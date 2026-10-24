const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';

/** Initialize the Home Hero scene selector; scenes change only on user input. */
export function initHomeHero() {
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

  let transitionTimeout = 0;
  let firstFrame = 0;
  let secondFrame = 0;

  const clearPendingTransition = () => {
    window.clearTimeout(transitionTimeout);
    window.cancelAnimationFrame(firstFrame);
    window.cancelAnimationFrame(secondFrame);
  };

  const updateVisual = (src, key, avifSrcset, webpSrcset) => {
    visual.dataset.visualKey = key;
    if (!src) return;

    const currentImage = visual.querySelector('.hero-slide-visual__image');
    if (currentImage?.getAttribute('src') === src) return;

    const image = currentImage || document.createElement('img');
    const avifSource = visual.querySelector('source[type="image/avif"]');
    const webpSource = visual.querySelector('source[type="image/webp"]');

    if (!currentImage) {
      image.className = 'hero-slide-visual__image';
      image.alt = '';
      image.setAttribute('aria-hidden', 'true');
      image.decoding = 'async';
      image.width = 1122;
      image.height = 1402;
      visual.append(image);
    } else {
      image.removeAttribute('loading');
      image.removeAttribute('fetchpriority');
    }

    if (avifSource && avifSrcset) avifSource.srcset = avifSrcset;
    if (webpSource && webpSrcset) webpSource.srcset = webpSrcset;
    image.src = src;
  };

  const applyScene = (button) => {
    const { heroSlide, title: nextTitle, copy: nextCopy, ctaLabel: nextLabel, ctaUrl, background, titleColor, accent, visual: nextVisual, visualAvifSrcset, visualWebpSrcset } = button.dataset;

    hero.dataset.activeSlide = heroSlide;
    hero.style.setProperty('--hero-background', background);
    hero.style.setProperty('--hero-title-color', titleColor);
    hero.style.setProperty('--hero-accent', accent);
    title.textContent = nextTitle;
    copy.textContent = nextCopy;
    cta.href = ctaUrl;
    ctaLabel.textContent = nextLabel;
    updateVisual(nextVisual, heroSlide, visualAvifSrcset, visualWebpSrcset);
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
