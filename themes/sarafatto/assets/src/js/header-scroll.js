const SCROLL_THRESHOLD = 64;

export function initHeaderScroll() {
  const header = document.querySelector('.site-header');
  const panel = header?.querySelector('.site-header__panel');
  const trigger = header?.querySelector('.site-header__toggle');

  if (!header || !panel || !trigger) return false;

  let frameRequested = false;

  const syncDrawerState = () => {
    const isOpen = (
      panel.classList.contains('is-open')
      || panel.classList.contains('is-closing')
      || trigger.getAttribute('aria-expanded') === 'true'
    );

    header.classList.toggle('is-menu-open', isOpen);
  };

  const observer = new MutationObserver(syncDrawerState);
  observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
  observer.observe(trigger, { attributes: true, attributeFilter: ['aria-expanded'] });
  syncDrawerState();

  const updateHeader = () => {
    frameRequested = false;

    // The shared header stays sticky and visible while scrolling. The Home Hero
    // timeline owns its scroll state while the introductory pin is active.
    if (header.dataset.heroScrollActive === 'true') return;

    header.classList.remove('is-hidden');
    header.classList.toggle('is-scrolled', window.scrollY > SCROLL_THRESHOLD);
  };

  const requestHeaderUpdate = () => {
    if (frameRequested) return;
    frameRequested = true;
    window.requestAnimationFrame(updateHeader);
  };

  window.addEventListener('scroll', requestHeaderUpdate, { passive: true });
  window.addEventListener('pageshow', requestHeaderUpdate);
  updateHeader();

  return true;
}
