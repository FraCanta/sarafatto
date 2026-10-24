import { gsap, ScrollTrigger } from './motion-runtime.js';

const HERO_SCROLL_TRIGGER_ID = 'sarafatto-home-hero-scroll';
let heroScrollMedia;

/** Drive the Home Hero and its existing header from one reversible scroll timeline. */
export function initHomeHeroScroll() {
  const hero = document.querySelector('.site-main--home .hero-slider');
  const title = hero?.querySelector('[data-hero-title]');
  const visual = hero?.querySelector('[data-hero-visual]');
  const header = document.querySelector('.site-header');
  if (!hero || !title || !visual || !header) return false;

  heroScrollMedia?.revert();
  ScrollTrigger.getById(HERO_SCROLL_TRIGGER_ID)?.kill();

  const scrollMedia = gsap.matchMedia();
  heroScrollMedia = scrollMedia;

  scrollMedia.add(
    {
      desktop: '(min-width: 64rem) and (prefers-reduced-motion: no-preference)',
      tablet: '(min-width: 48rem) and (max-width: 63.999rem) and (prefers-reduced-motion: no-preference)',
      mobile: '(max-width: 47.999rem) and (prefers-reduced-motion: no-preference)',
    },
    (context) => {
      const { desktop, tablet, mobile } = context.conditions;
      const profile = desktop
        ? { pin: 0.7, finalWidth: 0.84, finalHeight: 0.96, titleScale: 0.82, visualScale: 0.95 }
        : tablet
          ? { pin: 0.58, finalWidth: 0.88, finalHeight: 0.97, titleScale: 0.88, visualScale: 0.96 }
          : { pin: 0.42, finalWidth: null, finalHeight: 0.92, titleScale: 0.9 };

      const initialRadius = Number.parseFloat(getComputedStyle(hero).borderTopLeftRadius) || 28;
      const pinTarget = hero.closest('.home-hero-scroll-frame') || hero;
      const compactHeaderHeight = desktop ? '7rem' : '4.5rem';
      const startHeaderSize = getComputedStyle(header).getPropertyValue('--header-compact-size').trim();
      const clearScrollState = () => {
        delete hero.dataset.scrollAnimationActive;
        delete header.dataset.heroScrollActive;
        header.classList.remove('is-hidden');
      };
      const beginScrollState = () => {
        hero.dataset.scrollAnimationActive = 'true';
        header.dataset.heroScrollActive = 'true';
        header.classList.remove('is-hidden');
      };

      const timeline = gsap.timeline({
        defaults: { ease: 'none' },
        scrollTrigger: {
          id: HERO_SCROLL_TRIGGER_ID,
          trigger: hero,
          start: 'top top',
          end: () => `+=${Math.round(window.innerHeight * profile.pin)}`,
          scrub: true,
          pin: pinTarget,
          pinSpacing: true,
          anticipatePin: 1,
          invalidateOnRefresh: true,
          onEnter: beginScrollState,
          onEnterBack: beginScrollState,
          onUpdate: (self) => {
            if (!self.isActive) return;
            header.classList.toggle('is-scrolled', self.progress >= 0.3);
            header.classList.remove('is-hidden');
          },
          onLeave: () => {
            clearScrollState();
            header.classList.add('is-scrolled');
            header.classList.remove('is-hidden');
          },
          onLeaveBack: () => {
            clearScrollState();
            header.classList.remove('is-scrolled', 'is-hidden');
          },
        },
      });

      const titleDuration = mobile ? 0.18 : 0.25;
      const cardStart = 0.2;
      const cardEnd = mobile ? 0.58 : 0.7;
      const visualEnd = mobile ? 0.65 : 0.75;
      const viewportWidth = () => document.documentElement.clientWidth;
      const heroViewportGap = () => (
        Number.parseFloat(getComputedStyle(hero).marginTop) || 0
      );
      const heroStartWidth = () => `${viewportWidth() - heroViewportGap() * 2}px`;
      const rootFontSize = () => Number.parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      const desktopHeroWidth = (ratio) => Math.min(viewportWidth() * ratio, 112 * rootFontSize());

      timeline.to(title, {
        scale: profile.titleScale,
        opacity: 0,
        y: mobile ? -6 : -15,
        duration: titleDuration,
      }, 0);

      if (mobile) {
        timeline.fromTo(hero, {
          width: heroStartWidth,
          minHeight: () => `${hero.getBoundingClientRect().height}px`,
        }, {
          width: () => `${viewportWidth() - rootFontSize() * 3}px`,
          minHeight: () => `${Math.round(hero.getBoundingClientRect().height * profile.finalHeight)}px`,
          borderRadius: `${initialRadius + 7}px`,
          duration: cardEnd - cardStart,
        }, cardStart);
      } else {
        timeline.fromTo(hero, {
          width: heroStartWidth,
        }, {
          width: () => `${desktopHeroWidth(profile.finalWidth)}px`,
          scaleY: profile.finalHeight,
          borderRadius: `${initialRadius + (desktop ? 12 : 8)}px`,
          duration: cardEnd - cardStart,
        }, cardStart);
      }

      if (!mobile) {
        timeline.to(visual, {
          scale: profile.visualScale,
          y: 5,
          duration: visualEnd - 0.35,
        }, 0.35);
      }

      timeline.fromTo(header, {
        y: mobile ? -6 : -10,
        autoAlpha: 0.82,
        '--header-compact-size': startHeaderSize,
      }, {
        y: 0,
        autoAlpha: 1,
        '--header-compact-size': compactHeaderHeight,
        duration: 0.15,
        immediateRender: false,
      }, 0.3);

      // Keep the compact Hero at its final state while the pin finishes.
      timeline.to({}, {
        duration: 1 - Math.max(cardEnd, visualEnd),
      }, Math.max(cardEnd, visualEnd));

      const refresh = () => ScrollTrigger.refresh();
      visual.addEventListener('load', refresh, true);
      window.addEventListener('load', refresh, { once: true });

      return () => {
        visual.removeEventListener('load', refresh, true);
        window.removeEventListener('load', refresh);
        clearScrollState();
        header.classList.remove('is-hidden');
        header.classList.toggle('is-scrolled', window.scrollY > 64);
      };
    },
  );

  return true;
}
