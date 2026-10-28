"""PayPal Orders v2.

The app opens the order's approval link in the system browser. PayPal sends the
parent back to ``paypal_return``, which captures the order; the
``PAYMENT.CAPTURE.COMPLETED`` webhook covers the parent who closes the browser
first. Webhooks are verified with PayPal's verify-webhook-signature API.
"""

from __future__ import annotations

import frappe
import requests
from frappe import _
from frappe.utils import cint

from cbc_ai_tutor.api import common

TIMEOUT = 30
HOSTS = {"Sandbox": "https://api-m.sandbox.paypal.com", "Live": "https://api-m.paypal.com"}


class PayPalError(frappe.ValidationError):
	pass


def enabled() -> bool:
	return bool(
		cint(common.setting("paypal_enabled", 0))
		and common.setting("paypal_client_id")
		and common.secret("paypal_client_secret")
	)


def _base() -> str:
	return HOSTS.get(common.setting("paypal_environment", "Sandbox"), HOSTS["Sandbox"])


def currency() -> str:
	return (common.setting("paypal_currency") or "USD").upper()


def _token() -> str:
	cache_key = f"cbc_paypal_token:{common.setting('paypal_environment', 'Sandbox')}"
	token = frappe.cache.get_value(cache_key)
	if token:
		return token
	client_id = common.setting("paypal_client_id")
	secret = common.secret("paypal_client_secret")
	if not client_id or not secret:
		raise PayPalError(_("PayPal is not set up yet."))
	try:
		response = requests.post(
			f"{_base()}/v1/oauth2/token",
			data={"grant_type": "client_credentials"},
			auth=(client_id, secret),
			headers={"Accept": "application/json"},
			timeout=TIMEOUT,
		)
	except requests.RequestException:
		raise PayPalError(_("PayPal could not be reached. Try again."))
	if not response.ok:
		frappe.log_error(title=f"PayPal token {response.status_code}", message=response.text[:2000])
		raise PayPalError(_("PayPal rejected the app's credentials. An administrator needs to check CBC Settings."))
	data = response.json()
	token = data["access_token"]
	frappe.cache.set_value(cache_key, token, expires_in_sec=max(60, cint(data.get("expires_in")) - 300))
	return token


def _request(method: str, path: str, **kwargs) -> requests.Response:
	headers = kwargs.pop("headers", {})
	headers.update({"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"})
	try:
		return requests.request(method, f"{_base()}{path}", headers=headers, timeout=TIMEOUT, **kwargs)
	except requests.RequestException:
		raise PayPalError(_("PayPal could not be reached. Try again."))


def create_order(reference: str, amount: float, description: str, return_url: str, cancel_url: str) -> dict:
	body = {
		"intent": "CAPTURE",
		"purchase_units": [
			{
				"reference_id": reference,
				"custom_id": reference,
				"invoice_id": reference,
				"description": description[:127],
				"amount": {"currency_code": currency(), "value": f"{amount:.2f}"},
			}
		],
		"payment_source": {
			"paypal": {
				"experience_context": {
					"brand_name": (common.setting("app_name") or "CBC AI Tutor")[:127],
					"shipping_preference": "NO_SHIPPING",
					"user_action": "PAY_NOW",
					"return_url": return_url,
					"cancel_url": cancel_url,
				}
			}
		},
	}
	response = _request("POST", "/v2/checkout/orders", json=body, headers={"PayPal-Request-Id": reference})
	if not response.ok:
		frappe.log_error(title=f"PayPal create order {response.status_code}", message=response.text[:2000])
		raise PayPalError(_("PayPal could not start the payment. Try again."))
	return response.json()


def approve_link(order: dict) -> str | None:
	for link in order.get("links") or []:
		if link.get("rel") in ("payer-action", "approve"):
			return link.get("href")
	return None


def get_order(order_id: str) -> dict:
	response = _request("GET", f"/v2/checkout/orders/{order_id}")
	if not response.ok:
		raise PayPalError(_("Could not check the PayPal payment."))
	return response.json()


def capture(order_id: str) -> dict:
	response = _request("POST", f"/v2/checkout/orders/{order_id}/capture", headers={"PayPal-Request-Id": f"cap-{order_id}"})
	if response.status_code == 422:
		data = response.json()
		issue = ((data.get("details") or [{}])[0]).get("issue")
		if issue == "ORDER_ALREADY_CAPTURED":
			return get_order(order_id)
		if issue in ("INSTRUMENT_DECLINED", "PAYER_ACTION_REQUIRED"):
			raise PayPalError(_("PayPal declined the payment method. Try another card or account."))
		if issue == "ORDER_NOT_APPROVED":
			return get_order(order_id)
	if not response.ok:
		frappe.log_error(title=f"PayPal capture {response.status_code}", message=response.text[:2000])
		raise PayPalError(_("PayPal could not complete the payment."))
	return response.json()


def completed_capture(order: dict) -> dict | None:
	"""The completed capture on an order, if there is one."""
	for unit in order.get("purchase_units") or []:
		for cap in ((unit.get("payments") or {}).get("captures")) or []:
			if cap.get("status") == "COMPLETED":
				return {
					"id": cap.get("id"),
					"amount": float((cap.get("amount") or {}).get("value") or 0),
					"currency": (cap.get("amount") or {}).get("currency_code"),
					"reference": unit.get("custom_id") or unit.get("reference_id"),
				}
	return None


def verify_webhook(headers, event: dict) -> bool:
	webhook_id = common.setting("paypal_webhook_id")
	if not webhook_id:
		return False
	body = {
		"auth_algo": headers.get("Paypal-Auth-Algo"),
		"cert_url": headers.get("Paypal-Cert-Url"),
		"transmission_id": headers.get("Paypal-Transmission-Id"),
		"transmission_sig": headers.get("Paypal-Transmission-Sig"),
		"transmission_time": headers.get("Paypal-Transmission-Time"),
		"webhook_id": webhook_id,
		"webhook_event": event,
	}
	if not all(body.values()):
		return False
	response = _request("POST", "/v1/notifications/verify-webhook-signature", json=body)
	return response.ok and (response.json() or {}).get("verification_status") == "SUCCESS"
