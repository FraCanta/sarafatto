import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

/** Animate the Home customisation ribbon and image in response to scroll. */
export function initHomePersonalized() {
  const section = document.querySelector('.site-main--home .home-personalized');
  const stage = section?.querySelector('.home-personalized__stage');
  const ribbon = section?.querySelector('[data-personalized-ribbon-track]');
  const ribbonPaths = Array.from(section?.querySelectorAll('[data-personalized-ribbon-path]') || []);
  const image = section?.querySelector('.home-personalized__image');

  if (!section || !stage || !ribbon || ribbonPaths.length === 0 || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;

  const media = gsap.matchMedia();
  media.add('(prefers-reduced-motion: no-preference)', () => {
    const isMobile = window.matchMedia('(max-width: 47.999rem)').matches;
    ribbonPaths.forEach((path) => {
      const pathLength = path.getTotalLength();
      gsap.set(path, { strokeDasharray: pathLength, strokeDashoffset: pathLength });
    });

    gsap.set(ribbon, { transformOrigin: 'left center' });

    const timeline = gsap.timeline({
      scrollTrigger: {
        trigger: stage,
        start: 'center center',
        end: '+=720',
        scrub: true,
        pin: stage,
        anticipatePin: 1,
        invalidateOnRefresh: true,
      },
    });

    timeline.to(ribbonPaths, { strokeDashoffset: 0, duration: 0.9, ease: 'none' }, 0);
    timeline.fromTo(ribbon, {
      scaleX: isMobile ? 0.985 : 0.96,
      scaleY: 0.97,
    }, {
      scaleX: 1.025,
      scaleY: 1,
      duration: 0.86,
      ease: 'none',
    }, 0);
    timeline.to(ribbon, { scaleX: 1, duration: 0.14, ease: 'none' }, 0.86);

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
