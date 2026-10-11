const getFocusableElements = (container) => Array.from(
  container.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'),
).filter((element) => (
  !element.closest('[hidden], [inert], [aria-hidden="true"]')
  && element.getClientRects().length > 0
));

const parseTime = (value) => {
  const time = value.trim();
  const amount = Number.parseFloat(time) || 0;
  return time.endsWith('ms') ? amount : amount * 1000;
};

const getTransformTransitionDuration = (element) => {
  const style = window.getComputedStyle(element);
  const properties = style.transitionProperty.split(',');
  const durations = style.transitionDuration.split(',');
  const delays = style.transitionDelay.split(',');

  return properties.reduce((maximum, property, index) => {
    if (property.trim() !== 'transform' && property.trim() !== 'all') return maximum;
    const duration = parseTime(durations[index % durations.length]);
    const delay = parseTime(delays[index % delays.length]);
    return Math.max(maximum, duration + delay);
  }, 0);
};

const waitForTransformTransition = (element) => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return Promise.resolve();

  const duration = getTransformTransitionDuration(element);
  if (!duration) return Promise.resolve();

  return new Promise((resolve) => {
    let fallbackTimer;
    const finish = () => {
      window.clearTimeout(fallbackTimer);
      element.removeEventListener('transitionend', onTransitionEnd);
      resolve();
    };
    const onTransitionEnd = (event) => {
      if (event.target === element && event.propertyName === 'transform') finish();
    };

    element.addEventListener('transitionend', onTransitionEnd);
    fallbackTimer = window.setTimeout(finish, duration + 80);
  });
};

const isUnmodifiedInternalLink = (event, anchor) => {
  if (
    event.defaultPrevented
    || event.button !== 0
    || event.metaKey
    || event.ctrlKey
    || event.shiftKey
    || event.altKey
    || anchor.hasAttribute('download')
    || (anchor.target && anchor.target.toLowerCase() !== '_self')
  ) return null;

  let destination;
  try {
    destination = new URL(anchor.href, window.location.href);
  } catch {
    return null;
  }

  if (
    destination.origin !== window.location.origin
    || !['http:', 'https:'].includes(destination.protocol)
  ) return null;

  return destination;
};

const navigateAfterClose = (destination, lenis) => {
  const current = new URL(window.location.href);
  const isSameDocument = (
    destination.pathname === current.pathname
    && destination.search === current.search
  );

  if (isSameDocument) {
    if (destination.hash) {
      if (destination.hash !== current.hash) window.history.pushState(null, '', destination.href);
      let id = destination.hash.slice(1);
      try {
        id = decodeURIComponent(id);
      } catch {
        // Keep the literal fragment if it contains malformed escape sequences.
      }
      const target = document.getElementById(id)
        || Array.from(document.getElementsByName(id))[0];
      if (target) {
        if (lenis) {
          lenis.scrollTo(target);
        } else {
          target.scrollIntoView();
        }
      }
    }
    return;
  }

  window.location.assign(destination.href);
};

export function initMobileMenu(lenis = null) {
  const trigger = document.querySelector('.site-header__toggle');
  const panel = document.getElementById('site-navigation-panel');
  const header = trigger?.closest('.site-header');

  if (!trigger || !panel || !header) return false;

  let previousOverflow = '';
  let previousPaddingRight = '';
  let scrollLocked = false;
  let menuState = 'closed';
  let transitionToken = 0;
  let closePromise = null;
  const desktopQuery = window.matchMedia('(min-width: 80rem)');

  const setDialogState = (open) => {
    if (open) {
      header.setAttribute('role', 'dialog');
      header.setAttribute('aria-modal', 'true');
      header.setAttribute('aria-labelledby', 'site-navigation-title');
    } else {
      header.removeAttribute('role');
      header.removeAttribute('aria-modal');
      header.removeAttribute('aria-labelledby');
    }
  };

  const lockScroll = () => {
    if (scrollLocked) return;
    scrollLocked = true;
    previousOverflow = document.body.style.overflow;
    previousPaddingRight = document.body.style.paddingRight;
    lenis?.stop();
    document.body.style.overflow = 'hidden';
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    if (scrollbarWidth > 0) document.body.style.paddingRight = `${scrollbarWidth}px`;
  };

  const unlockScroll = () => {
    if (!scrollLocked) return;
    scrollLocked = false;
    document.body.style.overflow = previousOverflow;
    document.body.style.paddingRight = previousPaddingRight;
    lenis?.start();
  };

  const openMenu = async () => {
    if (desktopQuery.matches || menuState === 'open' || menuState === 'opening') return;

    const token = ++transitionToken;
    menuState = 'opening';
    closePromise = null;
    lockScroll();
    // Keep the sticky header visible before the drawer's transition begins.
    header.classList.add('is-menu-open');
    header.classList.remove('is-hidden');
    panel.inert = true;
    panel.setAttribute('aria-hidden', 'true');
    setDialogState(true);
    trigger.setAttribute('aria-expanded', 'true');
    trigger.setAttribute('aria-label', trigger.dataset.closeLabel);
    panel.classList.add('is-visible');
    // Commit the visible, off-canvas start position before applying the open transform.
    void panel.offsetWidth;

    await new Promise((resolve) => window.requestAnimationFrame(resolve));
    if (token !== transitionToken || menuState !== 'opening') return;

    panel.classList.add('is-open');
    await waitForTransformTransition(panel);
    if (token !== transitionToken || menuState !== 'opening') return;

    menuState = 'open';
    panel.inert = false;
    panel.removeAttribute('aria-hidden');
    const firstMenuItem = panel.querySelector('.site-navigation a[href], .language-switcher a[href]');
    (firstMenuItem || trigger).focus();
  };

  const closeMenu = ({ restoreFocus = true } = {}) => {
    if (menuState === 'closed') return Promise.resolve();
    if (menuState === 'closing') return closePromise || Promise.resolve();

    const token = ++transitionToken;
    const shouldAnimate = panel.classList.contains('is-open');
    menuState = 'closing';
    panel.inert = true;
    panel.setAttribute('aria-hidden', 'true');
    panel.classList.add('is-closing');
    panel.classList.remove('is-open');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-label', trigger.dataset.openLabel);

    const transition = shouldAnimate ? waitForTransformTransition(panel) : Promise.resolve();
    closePromise = transition.then(() => {
      if (token !== transitionToken || menuState !== 'closing') return;

      menuState = 'closed';
      panel.classList.remove('is-visible', 'is-closing');
      header.classList.remove('is-menu-open');
      if (desktopQuery.matches) {
        panel.inert = false;
        panel.removeAttribute('aria-hidden');
      }
      setDialogState(false);
      unlockScroll();
      if (restoreFocus) trigger.focus();
      closePromise = null;
    });

    return closePromise;
  };

  trigger.addEventListener('click', () => {
    if (menuState === 'open' || menuState === 'opening') {
      closeMenu();
    } else {
      openMenu();
    }
  });

  header.querySelector('.site-header__whatsapp')?.addEventListener('click', () => {
    closeMenu({ restoreFocus: false });
  });

  panel.addEventListener('click', (event) => {
    if (menuState === 'closed') return;
    const anchor = event.target.closest('a[href]');
    if (!anchor) return;

    const destination = isUnmodifiedInternalLink(event, anchor);
    if (!destination) {
      closeMenu({ restoreFocus: false });
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    closeMenu({ restoreFocus: false }).then(() => navigateAfterClose(destination, lenis));
  });

  document.addEventListener('keydown', (event) => {
    if (menuState === 'closed') return;

    if (event.key === 'Escape') {
      event.preventDefault();
      closeMenu();
      return;
    }

    if (event.key !== 'Tab') return;
    const focusable = getFocusableElements(header);
    if (!focusable.length) {
      event.preventDefault();
      trigger.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || !header.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !header.contains(document.activeElement))) {
      event.preventDefault();
      first.focus();
    }
  });

  desktopQuery.addEventListener('change', (event) => {
    if (event.matches) {
      if (menuState !== 'closed') {
        closeMenu({ restoreFocus: false });
      } else {
        panel.classList.remove('is-visible', 'is-open', 'is-closing');
        panel.inert = false;
        panel.removeAttribute('aria-hidden');
      }

      if (header.contains(document.activeElement)) {
        const desktopTarget = panel.querySelector('.site-navigation a[href], .language-switcher a[href]')
          || document.querySelector('.site-header .custom-logo-link, .site-header .site-title');
        desktopTarget?.focus();
      }
      return;
    }

    if (menuState === 'closed') {
      panel.classList.remove('is-visible', 'is-open', 'is-closing');
      panel.inert = true;
      panel.setAttribute('aria-hidden', 'true');
    }
    if (header.contains(document.activeElement)) trigger.focus();
  });

  if (desktopQuery.matches) {
    panel.classList.remove('is-visible', 'is-open', 'is-closing');
    panel.inert = false;
    panel.removeAttribute('aria-hidden');
  } else {
    panel.classList.remove('is-visible', 'is-open', 'is-closing');
    panel.inert = true;
    panel.setAttribute('aria-hidden', 'true');
  }
  document.documentElement.classList.add('js');
  return true;
}
