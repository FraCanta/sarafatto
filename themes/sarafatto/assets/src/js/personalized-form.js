/** Accessible, progressive three-step personalisation request form. */
export function initPersonalizedForm() {
  const form = document.querySelector('[data-personalized-request-form]');
  if (!form) return;

  const steps = [...form.querySelectorAll('[data-request-step]')];
  const progress = [...document.querySelectorAll('[data-request-progress]')];
  const submitButton = form.querySelector('[data-submit-request]');
  const submitStatus = form.querySelector('[data-submit-status]');
  const otherProduct = form.querySelector('[data-other-product]');
  const otherProductInput = form.querySelector('#personalized-other-product');

  if (steps.length !== 3 || !submitButton) return;

  const english = document.documentElement.lang.toLowerCase().startsWith('en');
  const labels = english
    ? {
        required: 'Complete this field to continue.',
        email: 'Enter a valid email address.',
        quantity: 'Enter a quantity between 1 and 999.',
        privacy: 'Accept the privacy notice to send your request.',
        product: 'Choose a product or select that you would like advice.',
      }
    : {
        required: 'Compila questo campo per continuare.',
        email: 'Inserisci un indirizzo email valido.',
        quantity: 'Inserisci una quantità da 1 a 999.',
        privacy: 'Accetta l’informativa privacy per inviare la richiesta.',
        product: 'Scegli un prodotto oppure indica che vuoi un consiglio.',
      };
  let currentStep = 0;
  let isSubmitting = false;

  const getFieldError = (field) => {
    const namedError = form.querySelector(`[data-field-error="${field.name}"]`);
    if (namedError) return namedError;
    if (field.type === 'radio' && field.name === 'personalized_product') return form.querySelector('[data-field-error="personalized_product"]');
    return null;
  };

  const clearError = (field) => {
    field.removeAttribute('aria-invalid');
    const error = getFieldError(field);
    if (error) {
      error.hidden = true;
      error.textContent = '';
    }
    if (field.type === 'radio' && field.name === 'personalized_product') {
      form.querySelectorAll('[name="personalized_product"]').forEach((radio) => radio.removeAttribute('aria-invalid'));
    }
  };

  const setError = (field) => {
    const error = getFieldError(field);
    field.setAttribute('aria-invalid', 'true');
    if (field.type === 'radio' && field.name === 'personalized_product') {
      form.querySelectorAll('[name="personalized_product"]').forEach((radio) => radio.setAttribute('aria-invalid', 'true'));
    }
    if (error) {
      const message = field.name === 'personalized_product'
        ? labels.product
        : field.name === 'personalized_privacy'
          ? labels.privacy
          : field.name === 'personalized_quantity'
            ? labels.quantity
            : field.type === 'email' && field.validity.typeMismatch
              ? labels.email
              : labels.required;
      error.textContent = message;
      error.hidden = false;
    }
  };

  const validateStep = (index) => {
    const invalidField = [...steps[index].querySelectorAll('input, textarea, select')]
      .find((field) => field.willValidate && !field.checkValidity());
    if (!invalidField) return true;
    setError(invalidField);
    invalidField.focus({ preventScroll: true });
    return false;
  };

  const updateSummary = () => {
    const selectedProduct = form.querySelector('[name="personalized_product"]:checked');
    const productLabel = selectedProduct?.closest('label')?.querySelector('span')?.textContent.trim() || '';
    const values = {
      product: productLabel,
      other_product: otherProductInput?.value.trim() || '',
      text: form.elements.personalized_text.value.trim(),
      font: form.elements.personalized_font.value.trim(),
      color: form.elements.personalized_color.value.trim(),
      style_notes: form.elements.personalized_style_notes.value.trim(),
      quantity: form.elements.personalized_quantity.value || '1',
      needed_by: form.elements.personalized_needed_by.value,
      name: form.elements.personalized_name.value.trim(),
      email: form.elements.personalized_email.value.trim(),
      phone: form.elements.personalized_phone.value.trim(),
      notes: form.elements.personalized_notes.value.trim(),
    };
    Object.entries(values).forEach(([key, value]) => {
      const output = form.querySelector(`[data-summary="${key}"]`);
      if (!output) return;
      output.textContent = value || (english ? 'Not specified' : 'Non indicato');
      const term = output.previousElementSibling;
      if (term?.tagName === 'DT') term.hidden = !value;
      output.hidden = !value;
    });
  };

  const showStep = (index, { focus = true } = {}) => {
    currentStep = index;
    steps.forEach((step, stepIndex) => {
      step.hidden = stepIndex !== index;
      step.querySelectorAll('[data-request-back]').forEach((button) => { button.hidden = index === 0; });
      step.querySelectorAll('[data-request-next]').forEach((button) => { button.hidden = index === steps.length - 1; });
    });
    form.querySelectorAll('[data-edit-step]').forEach((button) => { button.hidden = index !== steps.length - 1; });
    progress.forEach((item, stepIndex) => {
      if (stepIndex === index) item.setAttribute('aria-current', 'step');
      else item.removeAttribute('aria-current');
    });
    if (index === 2) updateSummary();
    if (focus) steps[index].querySelector('.personalized-page__step-title')?.focus({ preventScroll: true });
  };

  const syncOtherProductField = () => {
    const isOther = form.querySelector('[name="personalized_product"]:checked')?.value === 'other';
    if (otherProduct) otherProduct.hidden = !isOther;
    if (otherProductInput) {
      otherProductInput.required = isOther;
      if (!isOther) clearError(otherProductInput);
    }
  };

  form.noValidate = true;
  form.querySelectorAll('[data-request-next], [data-request-back], [data-edit-step]').forEach((button) => { button.hidden = true; });
  form.querySelector('.personalized-page__summary')?.removeAttribute('hidden');
  steps[0].querySelectorAll('[data-request-next]').forEach((button) => { button.hidden = false; });
  syncOtherProductField();
  showStep(0, { focus: false });

  form.addEventListener('input', (event) => {
    if (event.target.matches('input, textarea, select')) clearError(event.target);
  });
  form.addEventListener('change', (event) => {
    if (event.target.matches('input, textarea, select')) clearError(event.target);
    if (event.target.name === 'personalized_product') syncOtherProductField();
  });

  form.querySelectorAll('[data-request-next]').forEach((button) => {
    button.addEventListener('click', () => {
      if (!validateStep(currentStep)) return;
      showStep(Math.min(currentStep + 1, steps.length - 1));
    });
  });
  form.querySelectorAll('[data-request-back]').forEach((button) => {
    button.addEventListener('click', () => showStep(Math.max(currentStep - 1, 0)));
  });
  form.querySelectorAll('[data-edit-step]').forEach((button) => {
    button.addEventListener('click', () => showStep(Number(button.dataset.editStep) - 1));
  });

  form.addEventListener('submit', (event) => {
    if (isSubmitting) {
      event.preventDefault();
      return;
    }
    if (!validateStep(2)) {
      event.preventDefault();
      return;
    }
    isSubmitting = true;
    form.setAttribute('aria-busy', 'true');
    submitButton.disabled = true;
    if (submitStatus) submitStatus.hidden = false;
  });
}
