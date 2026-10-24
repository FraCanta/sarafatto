import './app.js';

import { initProductArchiveHero } from './product-archive-hero.js';
import { initSmoothScroll } from './smooth-scroll.js';
import { connectLenisToScrollTrigger } from './motion-runtime.js';

const lenis = initSmoothScroll();
connectLenisToScrollTrigger(lenis);
initProductArchiveHero();
