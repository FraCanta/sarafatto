(function () {
	'use strict';

	document.addEventListener('DOMContentLoaded', function () {
		const imageId = document.getElementById('sarafatto-setting-home_personalized_image_id');
		const preview = document.querySelector('.sarafatto-home-personalized-image-preview');
		const selectButton = document.querySelector('.sarafatto-home-personalized-image-select');
		const removeButton = document.querySelector('.sarafatto-home-personalized-image-remove');
		const config = window.sarafattoHomePersonalizedMedia;

		if (!imageId || !preview || !selectButton || !removeButton || !window.wp || !wp.media || !config) {
			return;
		}

		let frame;
		selectButton.addEventListener('click', function (event) {
			event.preventDefault();
			if (!frame) {
				frame = wp.media({
					title: config.title,
					button: { text: config.useImage },
					library: { type: 'image' },
					multiple: false,
				});
				frame.on('select', function () {
					const attachment = frame.state().get('selection').first().toJSON();
					const source = attachment.sizes && attachment.sizes.medium ? attachment.sizes.medium.url : attachment.url;
					if (!attachment.id || !source) return;

					imageId.value = String(attachment.id);
					const image = document.createElement('img');
					image.src = source;
					image.alt = '';
					preview.replaceChildren(image);
					selectButton.textContent = config.replaceLabel;
					removeButton.hidden = false;
				});
			}
			frame.open();
		});

		removeButton.addEventListener('click', function (event) {
			event.preventDefault();
			imageId.value = '0';
			preview.replaceChildren();
			selectButton.textContent = config.selectLabel;
			removeButton.hidden = true;
			selectButton.focus();
		});
	});
})();
