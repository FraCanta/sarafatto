/** Global front-end entry point; page-specific behavior lives in its own entry. */
import '../css/app.css';
import { initMobileMenu } from './mobile-menu.js';
import { initPrimarySubmenus } from './primary-submenus.js';
import { initHeaderScroll } from './header-scroll.js';
import { initSmoothScroll } from './smooth-scroll.js';

initSmoothScroll();

initPrimarySubmenus();
initMobileMenu();
initHeaderScroll();

if (document.querySelector('[data-standard-page-hero]')) {
  import('./standard-page-hero.js').then(({ initStandardPageHeroes }) => initStandardPageHeroes());
}

if (document.querySelector('[data-personalized-request-form]')) {
  import('./personalized-form.js').then(({ initPersonalizedForm }) => initPersonalizedForm());
}
