// The Nokia 7 Plus ships WebView 84. These methods arrived later, and Vite's
// syntax target does not rewrite method calls.
if (!String.prototype.replaceAll) {
  String.prototype.replaceAll = function (search, replacement) {
    if (search instanceof RegExp) {
      if (!search.global) throw new TypeError('replaceAll requires a global RegExp')
      return this.replace(search, replacement)
    }
    return this.split(search).join(replacement)
  }
}
if (!Object.hasOwn) {
  Object.hasOwn = (object, key) => Object.prototype.hasOwnProperty.call(object, key)
}
