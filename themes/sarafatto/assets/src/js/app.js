/** Global front-end entry point; page-specific behavior lives in its own entry. */
import '../css/app.css';
import { initMobileMenu } from './mobile-menu.js';
import { initPrimarySubmenus } from './primary-submenus.js';
import { initHeaderScroll } from './header-scroll.js';

initPrimarySubmenus();
initMobileMenu();
initHeaderScroll();
