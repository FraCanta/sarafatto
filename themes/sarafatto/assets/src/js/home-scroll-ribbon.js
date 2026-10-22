import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

/** Draw the Home brand ribbon in scroll progress, then gently move its text. */
export function initHomeScrollRibbon() {
  const ribbon = document.querySelector('.site-main--home .home-scroll-ribbon');
  const path = ribbon?.querySelector('#home-scroll-ribbon-path');
  const revealPath = ribbon?.querySelector('[data-ribbon-reveal-path]');
  const textPath = ribbon?.querySelector('[data-ribbon-marquee]');
  const elasticGroup = ribbon?.querySelector('[data-ribbon-elastic]');

  if (!ribbon || !path || !revealPath || !textPath || !elasticGroup) return false;

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;

  const pathLength = path.getTotalLength();
  const measure = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  measure.classList.add('home-scroll-ribbon__text');
  measure.textContent = 'SARÀ FATTO · ';
  ribbon.querySelector('.home-scroll-ribbon__art').appendChild(measure);
  const phraseLength = measure.getComputedTextLength();
  measure.remove();
  const initialDashOffset = pathLength * 0.82;
  gsap.set(revealPath, { strokeDasharray: pathLength, strokeDashoffset: initialDashOffset });
  gsap.set(elasticGroup, { transformOrigin: 'left center' });

  const marquee = gsap.to(textPath, {
    attr: { startOffset: -phraseLength },
    duration: 14,
    ease: 'none',
    repeat: -1,
    paused: true,
  });

  const timeline = gsap.timeline({
    scrollTrigger: {
      trigger: ribbon,
      start: 'top 90%',
      end: 'center center',
      scrub: 0.65,
      invalidateOnRefresh: true,
      onUpdate: ({ progress }) => {
        if (progress > 0.02) {
          if (!marquee.isActive()) marquee.play();
        } else {
          marquee.pause();
        }
      },
    },
  });

  timeline.fromTo(revealPath, {
    strokeDashoffset: initialDashOffset,
  }, {
    strokeDashoffset: 0,
    duration: 0.88,
    ease: 'none',
  }, 0);

  timeline.fromTo(elasticGroup, {
    scaleX: 0.985,
    scaleY: 0.975,
  }, {
    scaleX: 1.012,
    scaleY: 1,
    duration: 0.86,
    ease: 'none',
  }, 0);

  timeline.to(elasticGroup, {
    scaleX: 1,
    duration: 0.14,
    ease: 'none',
  }, 0.86);

  return true;
}
