(function ($, wp, l10n) {
	'use strict';

	$(function () {
		document.querySelectorAll('[data-sarafatto-demo-action]').forEach((button) => {
			button.addEventListener('click', () => {
				const nonce = document.getElementById('sarafatto_demo_nonce');
				if (!nonce || !nonce.value) return;

				const form = document.createElement('form');
				form.method = 'post';
				form.action = button.dataset.sarafattoDemoAction;
				form.hidden = true;
				[
					['post_id', button.dataset.productId],
					['sarafatto_demo_nonce', nonce.value],
				].forEach(([name, value]) => {
					const field = document.createElement('input');
					field.type = 'hidden';
					field.name = name;
					field.value = value;
					form.appendChild(field);
				});
				document.body.appendChild(form);
				form.requestSubmit();
			});
		});

		const personalizable = document.getElementById('sarafatto-personalizable');
		const customizationRow = document.getElementById('sarafatto-customization-details-row');
		if (personalizable && customizationRow) {
			const updateCustomizationVisibility = () => {
				customizationRow.hidden = !personalizable.checked;
			};
			personalizable.addEventListener('change', updateCustomizationVisibility);
			updateCustomizationVisibility();
		}

		const input = document.getElementById('sarafatto-gallery-ids');
		const preview = document.getElementById('sarafatto-gallery-preview');
		const addButton = document.getElementById('sarafatto-gallery-add');
		const status = document.getElementById('sarafatto-gallery-status');
		if (!input || !preview || !addButton || !wp || !wp.media) return;

		const selectedIds = () => input.value.split(',').map((value) => Number.parseInt(value, 10)).filter((value) => Number.isInteger(value) && value > 0);
		const render = (attachments) => {
			preview.replaceChildren();
			attachments.forEach((attachment) => {
				const item = document.createElement('li');
				item.className = 'sarafatto-gallery-preview__item';
				item.dataset.attachmentId = String(attachment.id);
				const image = document.createElement('img');
				image.src = attachment.url;
				image.alt = '';
				image.loading = 'lazy';
				item.appendChild(image);
				const remove = document.createElement('button');
				remove.type = 'button';
				remove.className = 'button-link-delete sarafatto-gallery-preview__remove';
				remove.textContent = l10n.remove;
				remove.setAttribute('aria-label', l10n.removeLabel.replace('%s', attachment.title || 'immagine'));
				item.appendChild(remove);
				preview.appendChild(item);
			});
			input.value = attachments.map((attachment) => attachment.id).join(',');
		};

		preview.addEventListener('click', (event) => {
			const button = event.target.closest('.sarafatto-gallery-preview__remove');
			if (!button) return;
			const item = button.closest('[data-attachment-id]');
			if (!item) return;
			item.remove();
			input.value = Array.from(preview.querySelectorAll('[data-attachment-id]')).map((element) => element.dataset.attachmentId).join(',');
			if (status) status.textContent = l10n.removed;
			(preview.querySelector('.sarafatto-gallery-preview__remove') || addButton).focus();
		});

		let frame;
		addButton.addEventListener('click', () => {
			if (!frame) {
				frame = wp.media({ title: l10n.title, button: { text: l10n.button }, library: { type: 'image' }, multiple: true });
				frame.on('open', () => {
					const selection = frame.state().get('selection');
					selection.reset();
					selectedIds().forEach((id) => { const attachment = wp.media.attachment(id); attachment.fetch(); selection.add(attachment); });
				});
				frame.on('select', () => {
					const attachments = new Map();
					Array.from(preview.querySelectorAll('[data-attachment-id]')).forEach((item) => {
						const image = item.querySelector('img');
						const id = Number.parseInt(item.dataset.attachmentId, 10);
						attachments.set(id, { id, title: '', url: image ? image.src : '' });
					});
					frame.state().get('selection').toJSON().forEach((attachment) => {
						if (attachments.has(attachment.id)) return;
						const thumbnail = attachment.sizes && attachment.sizes.thumbnail;
						const url = thumbnail ? thumbnail.url : attachment.url;
						if (url) attachments.set(attachment.id, { id: attachment.id, title: attachment.title, url });
					});
					render(Array.from(attachments.values()));
					if (status) status.textContent = l10n.updated;
				});
			}
			frame.open();
		});
	});
})(jQuery, window.wp, window.sarafattoProductGalleryL10n || {});
