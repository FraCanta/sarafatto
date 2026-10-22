import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';
const HERO_SCROLL_TRIGGER_ID = 'sarafatto-home-hero-scroll';

gsap.registerPlugin(ScrollTrigger);

let heroScrollMedia;

/** Initialize the Home Hero scene selector; scenes change only on user input. */
export function initHomeHero(lenis = null) {
  const hero = document.querySelector('.site-main--home .hero-slider');
  if (!hero) return false;

  const title = hero.querySelector('[data-hero-title]');
  const visual = hero.querySelector('[data-hero-visual]');
  const copy = hero.querySelector('[data-hero-copy]');
  const cta = hero.querySelector('[data-hero-cta]');
  const ctaLabel = hero.querySelector('[data-hero-cta-label]');
  const buttons = Array.from(hero.querySelectorAll('[data-hero-slide]'));
  if (!title || !visual || !copy || !cta || !ctaLabel || buttons.length < 2) return false;

  const reducedMotion = window.matchMedia(REDUCED_MOTION);

  initHomeHeroScroll({ hero, title, visual, lenis });

  let transitionTimeout = 0;
  let firstFrame = 0;
  let secondFrame = 0;

  const clearPendingTransition = () => {
    window.clearTimeout(transitionTimeout);
    window.cancelAnimationFrame(firstFrame);
    window.cancelAnimationFrame(secondFrame);
  };

  const updateVisual = (src, key) => {
    visual.dataset.visualKey = key;
    if (!src) {
      const placeholder = document.createElement('div');
      placeholder.className = 'hero-slide-visual__placeholder';
      visual.replaceChildren(placeholder);
      return;
    }

    const image = document.createElement('img');
    image.className = 'hero-slide-visual__image';
    image.alt = '';
    image.setAttribute('aria-hidden', 'true');
    image.decoding = 'async';
    image.fetchPriority = 'high';
    image.src = src;
    visual.replaceChildren(image);
  };

  const applyScene = (button) => {
    const { heroSlide, title: nextTitle, copy: nextCopy, ctaLabel: nextLabel, ctaUrl, background, titleColor, accent, visual: nextVisual } = button.dataset;

    hero.dataset.activeSlide = heroSlide;
    hero.style.setProperty('--hero-background', background);
    hero.style.setProperty('--hero-title-color', titleColor);
    hero.style.setProperty('--hero-accent', accent);
    title.textContent = nextTitle;
    copy.textContent = nextCopy;
    cta.href = ctaUrl;
    ctaLabel.textContent = nextLabel;
    updateVisual(nextVisual, heroSlide);
  };

  const initialScene = buttons.find((button) => button.getAttribute('aria-pressed') === 'true') || buttons[0];
  applyScene(initialScene);

  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      if (button.getAttribute('aria-pressed') === 'true') return;

      clearPendingTransition();
      hero.removeAttribute('data-hero-entering');
      buttons.forEach((item) => {
        const active = item === button;
        item.classList.toggle('is-active', active);
        item.setAttribute('aria-pressed', String(active));
      });

      if (reducedMotion.matches) {
        applyScene(button);
        hero.removeAttribute('data-hero-transitioning');
        hero.removeAttribute('data-hero-entering');
        return;
      }

      hero.setAttribute('data-hero-transitioning', 'true');
      transitionTimeout = window.setTimeout(() => {
        applyScene(button);
        hero.removeAttribute('data-hero-transitioning');
        hero.setAttribute('data-hero-entering', 'true');
        firstFrame = window.requestAnimationFrame(() => {
          secondFrame = window.requestAnimationFrame(() => {
            hero.removeAttribute('data-hero-entering');
          });
        });
      }, 110);
    });
  });

  return true;
}

/** Drive the Home Hero and its existing header from one reversible scroll timeline. */
function initHomeHeroScroll({ hero, title, visual, lenis }) {
  const header = document.querySelector('.site-header');
  if (!header) return false;

  heroScrollMedia?.revert();
  ScrollTrigger.getById(HERO_SCROLL_TRIGGER_ID)?.kill();

  if (lenis) {
    lenis.on('scroll', ScrollTrigger.update);
  }

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
      const cardStart = mobile ? 0.2 : 0.2;
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
        }, {
          width: () => `${viewportWidth() - rootFontSize() * 3}px`,
          scaleY: profile.finalHeight,
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
