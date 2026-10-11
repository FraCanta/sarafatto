/** Lightweight accessible thumbnail switching for product detail galleries. */
export function initProductGallery() {
  document.querySelectorAll('[data-product-gallery]').forEach((gallery) => {
    const mainImage = gallery.querySelector('.product-gallery__image');
    const thumbnails = gallery.querySelectorAll('.product-gallery__thumb');

    if (!mainImage || thumbnails.length < 2) return;

    thumbnails.forEach((thumbnail) => {
      thumbnail.addEventListener('click', () => {
        const { gallerySrc, gallerySrcset, gallerySizes, galleryAlt } = thumbnail.dataset;
        if (!gallerySrc) return;

        mainImage.src = gallerySrc;
        if (gallerySrcset) mainImage.srcset = gallerySrcset;
        else mainImage.removeAttribute('srcset');
        if (gallerySizes) mainImage.sizes = gallerySizes;
        if (galleryAlt) mainImage.alt = galleryAlt;

        thumbnails.forEach((item) => {
          const active = item === thumbnail;
          item.classList.toggle('is-active', active);
          item.setAttribute('aria-pressed', String(active));
        });
      });
    });
  });
}
