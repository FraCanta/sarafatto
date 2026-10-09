/** Front-end entry point. Add small, focused modules here as the project grows. */
import '../css/app.css';

import { initSmoothScroll } from './smooth-scroll.js';
import { initMobileMenu } from './mobile-menu.js';

const lenis = initSmoothScroll();

initMobileMenu(lenis);
