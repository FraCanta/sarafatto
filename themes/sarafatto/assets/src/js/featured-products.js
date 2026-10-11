/** Horizontal controls for the featured product rail. */
export function initFeaturedProducts() {
  document.querySelectorAll('[data-featured-list]').forEach((list) => {
    const getStep = () => {
      const item = list.querySelector('.home-featured__item');
      if (!item) return list.clientWidth;
      const gap = Number.parseFloat(getComputedStyle(list).columnGap) || 0;
      return item.getBoundingClientRect().width + gap;
    };

    list.closest('.home-featured__catalog')?.querySelectorAll('[data-featured-scroll]').forEach((button) => {
      button.addEventListener('click', () => {
        const direction = button.dataset.featuredScroll === 'prev' ? -1 : 1;
        list.scrollBy({ left: direction * getStep(), behavior: 'smooth' });
      });
    });
  });
}
