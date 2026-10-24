import './app.js';

import { initFeaturedProducts } from './featured-products.js';
import { initHomeHero } from './home-hero.js';
import { initHomeHeroScroll } from './home-hero-scroll.js';
import { initHomePersonalized } from './home-personalized.js';
import { initHomeServiceStrip } from './home-service-strip.js';
import { initHomeSectionReveals } from './home-section-reveals.js';
import { initHomeScrollRibbon } from './home-scroll-ribbon.js';
import { initSmoothScroll } from './smooth-scroll.js';
import { connectLenisToScrollTrigger } from './motion-runtime.js';

const lenis = initSmoothScroll();
connectLenisToScrollTrigger(lenis);

if (initHomeHero()) initHomeHeroScroll();
initFeaturedProducts();
initHomePersonalized();
initHomeServiceStrip();
initHomeSectionReveals();
initHomeScrollRibbon();
