const getFocusable = (container) => Array.from(
  container.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'),
).filter((element) => (
  !element.closest('[hidden], [inert], [aria-hidden="true"]')
  && element.getClientRects().length > 0
));

export function initPrimarySubmenus() {
  const navigation = document.querySelector('.site-navigation');
  const menuList = navigation?.querySelector('.site-navigation__list');
  if (!navigation || !menuList) return false;

  const desktopQuery = window.matchMedia('(min-width: 80rem)');
  const items = Array.from(menuList.querySelectorAll(':scope > .menu-item-has-children'));
  let activeMobileItem = null;
  let activeMobileLabel = null;
  let desktopCloseTimer = null;

  const getPanels = (item) => Array.from(item.querySelectorAll(':scope > .products-menu > .products-menu__desktop, :scope > .products-menu > .products-menu__mobile, :scope > .site-navigation__subview'));
  const getToggle = (item) => item.querySelector(':scope > .site-navigation__submenu-toggle');
  const getMobileView = (item) => item.querySelector(':scope > .products-menu > .products-menu__mobile, :scope > .site-navigation__subview');
  const getBackButton = (view) => view?.querySelector('.site-navigation__back');
  const clearDesktopClose = () => {
    if (desktopCloseTimer !== null) {
      window.clearTimeout(desktopCloseTimer);
      desktopCloseTimer = null;
    }
  };

  const setPanelState = (panel, open) => {
    if (!panel) return;
    panel.inert = !open;
    panel.setAttribute('aria-hidden', String(!open));
    if (panel.matches('.products-menu__mobile')) {
      panel.hidden = !open;
    }
    panel.classList.toggle('is-open', open);
  };

  const closeDesktopItem = (item, { dismissHover = false } = {}) => {
    clearDesktopClose();
    if (dismissHover) item.classList.add('is-submenu-dismissed');
    item.classList.remove('is-submenu-open');
    getToggle(item)?.setAttribute('aria-expanded', 'false');
    getPanels(item).filter((panel) => !panel.matches('.products-menu__mobile')).forEach((panel) => setPanelState(panel, false));
  };

  const scheduleDesktopClose = (item) => {
    clearDesktopClose();
    desktopCloseTimer = window.setTimeout(() => {
      desktopCloseTimer = null;
      if (!item.matches(':hover') && !item.contains(document.activeElement)) closeDesktopItem(item);
    }, 300);
  };

  const closeMobileView = (item, { restoreFocus = true, animate = false } = {}) => {
    const view = getMobileView(item);
    if (!view || view.classList.contains('is-closing')) return;

    let closeTimer = null;
    const onAnimationEnd = (event) => {
      if (event.target === view && event.animationName === 'submenu-drawer-enter') finishClose();
    };
    const finishClose = () => {
      window.clearTimeout(closeTimer);
      view.removeEventListener('animationend', onAnimationEnd);
      view.classList.remove('is-closing');
      setPanelState(view, false);
      if (activeMobileLabel?.item === item) {
        item.insertBefore(activeMobileLabel.element, getToggle(item));
        activeMobileLabel = null;
      }
      item.classList.remove('is-subview-open');
      menuList.classList.remove('is-subview-open');
      getToggle(item)?.setAttribute('aria-expanded', 'false');
      activeMobileItem = null;
      if (restoreFocus) getToggle(item)?.focus();
    };

    if (!animate || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      finishClose();
      return;
    }

    view.classList.remove('is-open');
    view.classList.add('is-closing');
    view.addEventListener('animationend', onAnimationEnd);
    const animationStyle = window.getComputedStyle(view);
    const toMilliseconds = (value) => {
      const time = Number.parseFloat(value) || 0;
      return value.trim().endsWith('ms') ? time : time * 1000;
    };
    const duration = Math.max(...animationStyle.animationDuration.split(',').map(toMilliseconds));
    const delay = Math.max(...animationStyle.animationDelay.split(',').map(toMilliseconds));
    closeTimer = window.setTimeout(finishClose, duration + delay + 50);
  };

  const openMobileView = (item) => {
    if (activeMobileItem && activeMobileItem !== item) closeMobileView(activeMobileItem, { restoreFocus: false });
    const view = getMobileView(item);
    if (!view) return;

    activeMobileItem = item;
    menuList.classList.add('is-subview-open');
    item.classList.add('is-subview-open');
    if (item.classList.contains('sarafatto-menu-products')) {
      const parentLabel = item.querySelector(':scope > .site-navigation__label');
      if (parentLabel) {
        activeMobileLabel = { item, element: parentLabel };
        parentLabel.remove();
      }
    }
    setPanelState(view, true);
    getToggle(item)?.setAttribute('aria-expanded', 'true');
    getBackButton(view)?.focus();
  };

  const openDesktopItem = (item) => {
    if (activeMobileItem) closeMobileView(activeMobileItem, { restoreFocus: false });
    item.classList.remove('is-submenu-dismissed');
    item.classList.add('is-submenu-open');
    getToggle(item)?.setAttribute('aria-expanded', 'true');
    getPanels(item).filter((panel) => !panel.matches('.products-menu__mobile')).forEach((panel) => setPanelState(panel, true));
  };

  items.forEach((item) => {
    const toggle = getToggle(item);
    const view = getMobileView(item);
    if (!toggle || !view) return;

    getPanels(item).forEach((panel) => setPanelState(panel, false));

    toggle.addEventListener('click', () => {
      if (!desktopQuery.matches) {
        if (activeMobileItem === item) {
          closeMobileView(item);
        } else {
          openMobileView(item);
        }
        return;
      }

      if (item.classList.contains('is-submenu-open')) {
        closeDesktopItem(item, { dismissHover: true });
      } else {
        items.forEach(closeDesktopItem);
        openDesktopItem(item);
      }
    });

    item.addEventListener('pointerenter', () => {
      if (desktopQuery.matches) {
        clearDesktopClose();
        openDesktopItem(item);
      }
    });

    getPanels(item)
      .filter((panel) => !panel.matches('.products-menu__mobile'))
      .forEach((panel) => {
        panel.addEventListener('pointerenter', () => {
          if (!desktopQuery.matches) return;
          clearDesktopClose();
          openDesktopItem(item);
        });
        panel.addEventListener('pointerleave', () => {
          if (desktopQuery.matches && !item.contains(document.activeElement)) scheduleDesktopClose(item);
        });
      });

    item.addEventListener('focusin', (event) => {
      if (!desktopQuery.matches) return;
      if (item.classList.contains('is-submenu-dismissed') && event.target === toggle) return;
      openDesktopItem(item);
    });

    item.addEventListener('pointerleave', () => {
      if (desktopQuery.matches && !item.contains(document.activeElement)) scheduleDesktopClose(item);
    });

    item.addEventListener('focusout', () => {
      window.requestAnimationFrame(() => {
        if (desktopQuery.matches && !item.matches(':hover') && !item.contains(document.activeElement)) closeDesktopItem(item);
      });
    });

    getBackButton(view)?.addEventListener('click', () => {
      if (activeMobileItem === item) closeMobileView(item, { animate: true });
    });
  });

  document.addEventListener('pointerdown', (event) => {
    if (!desktopQuery.matches) return;
    items.forEach((item) => {
      if (!item.contains(event.target)) closeDesktopItem(item);
    });
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      if (activeMobileItem) {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeMobileView(activeMobileItem, { animate: true });
        return;
      }

      const openItem = items.find((item) => item.classList.contains('is-submenu-open'));
      if (openItem) {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeDesktopItem(openItem, { dismissHover: true });
        getToggle(openItem)?.focus();
      }
      return;
    }

    if (!desktopQuery.matches || !['ArrowDown', 'ArrowUp'].includes(event.key)) return;
    const currentItem = event.target.closest('.site-navigation__list > .menu-item-has-children');
    if (!currentItem || !currentItem.classList.contains('is-submenu-open')) return;
    const visibleLinks = getFocusable(currentItem).filter((element) => element.matches('a[href]'));
    if (!visibleLinks.length) return;
    event.preventDefault();
    const nextIndex = event.key === 'ArrowDown' ? 0 : visibleLinks.length - 1;
    visibleLinks[nextIndex].focus();
  });

  document.querySelector('.site-header__toggle')?.addEventListener('click', () => {
    if (activeMobileItem) closeMobileView(activeMobileItem, { restoreFocus: false });
  });

  desktopQuery.addEventListener('change', (event) => {
    clearDesktopClose();
    if (activeMobileItem) closeMobileView(activeMobileItem, { restoreFocus: false });
    items.forEach(closeDesktopItem);
    if (!event.matches) {
      items.forEach((item) => getPanels(item).forEach((panel) => setPanelState(panel, false)));
    }
  });

  return true;
}
