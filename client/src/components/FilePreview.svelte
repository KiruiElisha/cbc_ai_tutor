<script>
  import { get, errorText, base64ToBlobUrl } from '../lib/tauri.js'
  import Modal from './Modal.svelte'

  /** `path` is 'sync.file' for learners, 'teacher.file' for teachers. */
  let { fileUrl, path = 'sync.file', label = 'Open file' } = $props()

  let open = $state(false)
  let busy = $state(false)
  let error = $state('')
  let file = $state(null)

  async function show() {
    open = true
    if (file) return
    busy = true
    error = ''
    try {
      const res = await get(path, { file_url: fileUrl })
      const ext = (res.file_name.split('.').pop() || '').toLowerCase()
      file = { name: res.file_name, url: base64ToBlobUrl(res.content, res.file_name), ext }
    } catch (e) {
      error = errorText(e)
    } finally {
      busy = false
    }
  }
</script>

<button class="btn ghost sm" type="button" onclick={show}>📎 {label}</button>

<Modal bind:open title={file?.name || 'File'}>
  {#if busy}
    <div class="loading"><span class="spinner"></span></div>
  {:else if error}
    <div class="banner bad">{error}</div>
  {:else if file}
    {#if ['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(file.ext)}
      <img src={file.url} alt={file.name} style="border-radius: 10px" />
    {:else if file.ext === 'pdf'}
      <iframe src={file.url} title={file.name} style="width: 100%; height: 70vh; border: 0"></iframe>
    {:else if ['mp3', 'm4a'].includes(file.ext)}
      <audio controls src={file.url} style="width: 100%"></audio>
    {:else}
      <p class="muted">This file type can't be shown in the app.</p>
    {/if}
    <a class="btn ghost sm" style="margin-top: 12px" href={file.url} download={file.name}>Save a copy</a>
  {/if}
</Modal>
