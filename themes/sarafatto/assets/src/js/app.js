/** Front-end entry point. Add small, focused modules here as the project grows. */
import '../css/app.css';

import { initSmoothScroll } from './smooth-scroll.js';
import { initMobileMenu } from './mobile-menu.js';
import { initPrimarySubmenus } from './primary-submenus.js';
import { initFeaturedProducts } from './featured-products.js';
import { initHeaderScroll } from './header-scroll.js';
import { initProductGallery } from './product-gallery.js';

const lenis = initSmoothScroll();

initPrimarySubmenus();
initMobileMenu(lenis);
initFeaturedProducts();
initHeaderScroll();
initProductGallery();
