const SCROLL_THRESHOLD = 64;
const DIRECTION_TOLERANCE = 10;

export function initHeaderScroll() {
  const header = document.querySelector('.site-header');
  const panel = header?.querySelector('.site-header__panel');
  const trigger = header?.querySelector('.site-header__toggle');

  if (!header || !panel || !trigger) return false;

  let lastScrollY = Math.max(0, window.scrollY);
  let accumulatedDirection = 0;
  let frameRequested = false;

  const drawerIsOpen = () => (
    panel.classList.contains('is-open')
    || panel.classList.contains('is-closing')
    || trigger.getAttribute('aria-expanded') === 'true'
  );

  const keepHeaderVisible = () => (
    drawerIsOpen()
    || Boolean(header.querySelector('.is-submenu-open'))
  );

  const syncDrawerState = () => {
    const isOpen = drawerIsOpen();
    header.classList.toggle('is-menu-open', isOpen);
    if (isOpen) {
      header.classList.remove('is-hidden');
      accumulatedDirection = 0;
    }
  };

  const observer = new MutationObserver(syncDrawerState);
  observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
  observer.observe(trigger, { attributes: true, attributeFilter: ['aria-expanded'] });
  syncDrawerState();

  const updateHeader = () => {
    frameRequested = false;
    const currentScrollY = Math.max(0, window.scrollY);
    const movement = currentScrollY - lastScrollY;
    lastScrollY = currentScrollY;

    if (header.dataset.heroScrollActive === 'true') {
      accumulatedDirection = 0;
      header.classList.remove('is-hidden');
      return;
    }

    if (currentScrollY <= SCROLL_THRESHOLD) {
      accumulatedDirection = 0;
      header.classList.remove('is-scrolled', 'is-hidden');
      return;
    }

    header.classList.add('is-scrolled');

    if (keepHeaderVisible()) {
      accumulatedDirection = 0;
      header.classList.remove('is-hidden');
      return;
    }

    accumulatedDirection += movement;
    if (accumulatedDirection >= DIRECTION_TOLERANCE) {
      header.classList.add('is-hidden');
      accumulatedDirection = 0;
    } else if (accumulatedDirection <= -DIRECTION_TOLERANCE) {
      header.classList.remove('is-hidden');
      accumulatedDirection = 0;
    }
  };

  const requestHeaderUpdate = () => {
    if (frameRequested) return;
    frameRequested = true;
    window.requestAnimationFrame(updateHeader);
  };

  header.addEventListener('focusin', () => {
    header.classList.remove('is-hidden');
  });
  window.addEventListener('scroll', requestHeaderUpdate, { passive: true });
  window.addEventListener('pageshow', () => {
    lastScrollY = Math.max(0, window.scrollY);
    accumulatedDirection = 0;
    header.classList.toggle('is-scrolled', lastScrollY > SCROLL_THRESHOLD);
    header.classList.remove('is-hidden');
  });

  header.classList.toggle('is-scrolled', lastScrollY > SCROLL_THRESHOLD);
  return true;
}
