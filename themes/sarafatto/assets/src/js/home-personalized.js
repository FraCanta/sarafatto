import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

/** Animate the Home customisation ribbon and image in response to scroll. */
export function initHomePersonalized() {
  const section = document.querySelector('.site-main--home .home-personalized');
  const ribbon = section?.querySelector('[data-personalized-ribbon-track]');
  const image = section?.querySelector('.home-personalized__image');

  if (!section || !ribbon || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;

  const media = gsap.matchMedia();
  media.add('(prefers-reduced-motion: no-preference)', () => {
    const isMobile = window.matchMedia('(max-width: 47.999rem)').matches;
    const startX = isMobile ? -28 : -48;

    gsap.set(ribbon, { transformOrigin: 'left center' });

    const timeline = gsap.timeline({
      scrollTrigger: {
        trigger: section,
        start: 'top 82%',
        end: 'bottom 28%',
        scrub: 0.65,
        invalidateOnRefresh: true,
      },
    });

    timeline.fromTo(ribbon, {
      xPercent: startX,
      scaleX: 0.76,
      scaleY: 0.9,
      rotation: isMobile ? -1.5 : -2.5,
    }, {
      xPercent: 0,
      scaleX: 1.06,
      scaleY: 1.02,
      rotation: 0,
      duration: 0.78,
      ease: 'power2.out',
    });

    timeline.to(ribbon, {
      scaleX: 1,
      scaleY: 1,
      duration: 0.22,
      ease: 'elastic.out(1, 0.72)',
    });

    if (image) {
      timeline.fromTo(image, {
        y: isMobile ? 18 : 28,
        scale: 0.97,
        opacity: 0.86,
      }, {
        y: 0,
        scale: 1,
        opacity: 1,
        duration: 0.72,
        ease: 'power2.out',
      }, 0.12);
    }

    return () => timeline.scrollTrigger?.kill();
  });

  return true;
}
