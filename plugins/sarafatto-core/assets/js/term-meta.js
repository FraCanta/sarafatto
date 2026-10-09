(function ($, wp, config) {
	'use strict';
	$(function () {
		document.querySelectorAll('.sarafatto-editorial-icon-select').forEach((select) => {
			select.addEventListener('change', () => {
				const preview = select.parentElement.querySelector('.sarafatto-editorial-icon-preview');
				if (!preview) return;
				preview.replaceChildren();
				if (!select.value) return;
				const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
				svg.setAttribute('class', 'sarafatto-editorial-icon');
				svg.setAttribute('viewBox', '0 0 24 24');
				svg.setAttribute('aria-hidden', 'true');
				const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
				use.setAttribute('href', `${config.spriteUrl}#${select.value}`);
				svg.appendChild(use);
				preview.appendChild(svg);
			});
		});

		document.querySelectorAll('.sarafatto-term-image-field').forEach((field) => {
			const input = field.querySelector('input[type="hidden"]');
			const preview = field.querySelector('.sarafatto-term-image-preview');
			const selectButton = field.querySelector('.sarafatto-term-image-select');
			const removeButton = field.querySelector('.sarafatto-term-image-remove');
			if (!input || !preview || !selectButton || !wp || !wp.media) return;
			let frame;
			selectButton.addEventListener('click', (event) => {
				event.preventDefault();
				if (!frame) {
					frame = wp.media({ title: config.messages.selectImage, button: { text: config.messages.useImage }, library: { type: 'image' }, multiple: false });
					frame.on('select', () => {
						const attachment = frame.state().get('selection').first().toJSON();
						const imageUrl = attachment.sizes && attachment.sizes.thumbnail ? attachment.sizes.thumbnail.url : attachment.url;
						if (!attachment.id || !imageUrl) return;
						input.value = String(attachment.id);
						const image = document.createElement('img');
						image.src = imageUrl;
						image.alt = '';
						preview.replaceChildren(image);
						if (removeButton) removeButton.hidden = false;
					});
				}
				frame.open();
			});
			if (removeButton) removeButton.addEventListener('click', (event) => {
				event.preventDefault();
				input.value = '0';
				preview.replaceChildren();
				removeButton.hidden = true;
				selectButton.focus();
			});
		});
	});
})(jQuery, window.wp, window.sarafattoTermMeta || { spriteUrl: '', messages: {} });
