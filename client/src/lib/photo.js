/**
 * A photo for Mwalimu, made small on the device first: phones take 3–12 MB pictures, and a
 * 1280-pixel JPEG reads just as well, sends in a second on a slow connection, and costs less.
 */
export async function shrinkPhoto(file, { side = 1280, quality = 0.82 } = {}) {
  if (!file || !file.type?.startsWith('image/')) throw new Error('Choose a photo.')
  const url = URL.createObjectURL(file)
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image()
      i.onload = () => resolve(i)
      i.onerror = () => reject(new Error('That photo could not be opened.'))
      i.src = url
    })
    const scale = Math.min(1, side / Math.max(img.naturalWidth, img.naturalHeight))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(img.naturalWidth * scale)
    canvas.height = Math.round(img.naturalHeight * scale)
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
    const dataUrl = canvas.toDataURL('image/jpeg', quality)
    return { dataUrl, preview: dataUrl }
  } finally {
    URL.revokeObjectURL(url)
  }
}
