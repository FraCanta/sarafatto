<?php
/** Editorial landing page for personalised products. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$request_url  = get_permalink( get_queried_object_id() );
$privacy_url  = function_exists( 'get_privacy_policy_url' ) ? get_privacy_policy_url() : '';
$product_options = function_exists( 'sarafatto_personalized_request_product_options' ) ? sarafatto_personalized_request_product_options() : array();
$request_status = isset( $_GET['personalized_request_status'] ) && is_scalar( $_GET['personalized_request_status'] ) ? sanitize_key( wp_unslash( $_GET['personalized_request_status'] ) ) : ''; // phpcs:ignore WordPress.Security.NonceVerification.Recommended
$request_status_text = array(
	'sent'        => sarafatto_theme_label( 'Richiesta inviata. Ti ricontatteremo per verificare disponibilità e dettagli.', 'Request sent. We’ll contact you to confirm availability and details.' ),
	'invalid'     => sarafatto_theme_label( 'Controlla i dati inseriti e accetta l’informativa privacy per inviare la richiesta.', 'Check your details and accept the privacy notice before sending.' ),
	'rate_limited' => sarafatto_theme_label( 'Hai inviato troppe richieste in poco tempo. Riprova più tardi.', 'Too many requests were sent in a short time. Please try again later.' ),
	'error'       => sarafatto_theme_label( 'Non è stato possibile inviare la richiesta. Riprova più tardi.', 'We could not send your request. Please try again later.' ),
);
$gallery = array(
	array(
		'image' => get_theme_file_uri( 'assets/images/home-personalized-shirt.png' ),
		'alt'   => sarafatto_theme_label( 'T-shirt personalizzata con una frase', 'T-shirt personalised with a phrase' ),
		'title' => sarafatto_theme_label( 'Frasi e citazioni', 'Phrases and quotes' ),
		'copy'  => sarafatto_theme_label( 'Le tue parole, su felpe, t-shirt e accessori.', 'Your words on sweatshirts, t-shirts and accessories.' ),
	),
	array(
		'image' => get_theme_file_uri( 'assets/images/home-saluti-da-qui.png' ),
		'alt'   => sarafatto_theme_label( 'Pochette con nome ricamato', 'Pouch with an embroidered name' ),
		'title' => sarafatto_theme_label( 'Nomi e iniziali', 'Names and initials' ),
		'copy'  => sarafatto_theme_label( 'Un dettaglio semplice che rende unico ogni prodotto.', 'A simple detail that makes every product unique.' ),
	),
	array(
		'image' => get_theme_file_uri( 'assets/images/home-kiki-borse.webp' ),
		'alt'   => sarafatto_theme_label( 'Borsa personalizzata', 'Personalised bag' ),
		'title' => sarafatto_theme_label( 'Idee su misura', 'Made-to-measure ideas' ),
		'copy'  => sarafatto_theme_label( 'Raccontaci la tua idea: la trasformiamo in realtà.', 'Tell us your idea: we’ll make it real.' ),
	),
);
$occasions = array(
	array( 'icon' => 'icon-[mdi--gift-outline]', 'label' => sarafatto_theme_label( 'Regali originali', 'Original gifts' ) ),
	array( 'icon' => 'icon-[mdi--heart-outline]', 'label' => sarafatto_theme_label( 'Occasioni speciali', 'Special occasions' ) ),
	array( 'icon' => 'icon-[mdi--account-group-outline]', 'label' => sarafatto_theme_label( 'Gruppi ed eventi', 'Groups and events' ) ),
	array( 'icon' => 'icon-[mdi--star-outline]', 'label' => sarafatto_theme_label( 'Idee fuori dal comune', 'Ideas out of the ordinary' ) ),
);
$reasons = array(
	array( 'icon' => 'icon-[mdi--diamond-stone]', 'title' => sarafatto_theme_label( 'È unico', 'It’s unique' ), 'copy' => sarafatto_theme_label( 'Nasce dalla tua idea.', 'It starts with your idea.' ) ),
	array( 'icon' => 'icon-[mdi--heart-outline]', 'title' => sarafatto_theme_label( 'È personale', 'It’s personal' ), 'copy' => sarafatto_theme_label( 'Racconta qualcosa di te o di chi lo riceve.', 'It says something about you or the person receiving it.' ) ),
	array( 'icon' => 'icon-[mdi--leaf]', 'title' => sarafatto_theme_label( 'È curato', 'It’s thoughtfully made' ), 'copy' => sarafatto_theme_label( 'Realizzato con attenzione e materiali di qualità.', 'Made with care and quality materials.' ) ),
);
$final_banner_image = get_theme_file_uri( 'assets/images/personalizzati-idea-banner.png' );
?>
<main id="main-content" class="site-main personalized-page" tabindex="-1">
	<?php while ( have_posts() ) : the_post(); ?>
		<?php
		get_template_part(
			'template-parts/components/page-hero',
			null,
			array(
				'title'       => get_the_title(),
				'breadcrumbs' => array(
					array( 'label' => sarafatto_theme_label( 'Home', 'Home' ), 'url' => function_exists( 'sarafatto_get_language_home_url' ) ? sarafatto_get_language_home_url() : home_url( '/' ) ),
					array( 'label' => get_the_title() ),
				),
			)
		);
	?>
	<?php endwhile; ?>

	<section class="personalized-page__perks" aria-labelledby="personalized-perks-title">
		<div class="container personalized-page__container">
			<h2 id="personalized-perks-title"><?php echo esc_html( sarafatto_theme_label( 'Perfetti per…', 'Perfect for…' ) ); ?></h2>
			<ul>
				<?php foreach ( $occasions as $occasion ) : ?>
					<li><span class="personalized-page__perk-icon <?php echo esc_attr( $occasion['icon'] ); ?>" aria-hidden="true"></span><?php echo esc_html( $occasion['label'] ); ?></li>
				<?php endforeach; ?>
			</ul>
		</div>
	</section>

	<section class="personalized-page__examples" aria-labelledby="personalized-examples-title">
		<div class="container personalized-page__container">
			<header class="personalized-page__section-heading">
				<h2 id="personalized-examples-title"><?php echo esc_html( sarafatto_theme_label( 'Qualche idea, per ispirarti', 'A few ideas to inspire you' ) ); ?></h2>
				<span class="personalized-page__underline" aria-hidden="true"></span>
			</header>
			<div class="personalized-page__gallery">
				<?php foreach ( $gallery as $item ) : ?>
					<article class="personalized-page__gallery-item">
						<img src="<?php echo esc_url( $item['image'] ); ?>" alt="<?php echo esc_attr( $item['alt'] ); ?>" loading="lazy" decoding="async" />
						<div class="personalized-page__gallery-copy"><h3><?php echo esc_html( $item['title'] ); ?></h3><p><?php echo esc_html( $item['copy'] ); ?></p></div>
					</article>
				<?php endforeach; ?>
			</div>
		</div>
	</section>

	<section class="personalized-page__request" id="contatti-form" aria-labelledby="personalized-request-title">
		<div class="container personalized-page__request-inner">
			<header class="personalized-page__section-heading">
				<h2 id="personalized-request-title"><?php echo esc_html( sarafatto_theme_label( 'Raccontaci la tua idea', 'Tell us your idea' ) ); ?></h2>
				<p><?php echo esc_html( sarafatto_theme_label( 'Compila il form: ci servirà per capire insieme cosa realizzare e prepararti una proposta su misura.', 'Fill in the form so we can decide what to create and prepare a proposal just for you.' ) ); ?></p>
			</header>
			<ol class="personalized-page__progress" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Avanzamento della richiesta', 'Request progress' ) ); ?>">
				<?php for ( $step = 1; $step <= 3; $step++ ) : ?><li data-request-progress="<?php echo esc_attr( (string) $step ); ?>"<?php echo 1 === $step ? ' aria-current="step"' : ''; ?>><span><?php echo esc_html( (string) $step ); ?></span></li><?php endfor; ?>
			</ol>
			<?php if ( isset( $request_status_text[ $request_status ] ) ) : ?><p class="personalized-page__form-notice" role="<?php echo 'sent' === $request_status ? 'status' : 'alert'; ?>" tabindex="-1"><?php echo esc_html( $request_status_text[ $request_status ] ); ?></p><?php endif; ?>
			<form class="personalized-page__form" data-personalized-request-form action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" method="post">
				<input type="hidden" name="action" value="sarafatto_personalized_request_submit">
				<input type="hidden" name="personalized_redirect_to" value="<?php echo esc_url( $request_url ); ?>">
				<?php wp_nonce_field( 'sarafatto_personalized_request', 'personalized_nonce' ); ?>
				<div class="personalized-page__trap" aria-hidden="true"><label for="personalized-website">Website</label><input id="personalized-website" type="text" name="personalized_website" tabindex="-1" autocomplete="off"></div>

				<fieldset class="personalized-page__step" data-request-step="1" aria-labelledby="personalized-step-one-title" aria-describedby="personalized-step-one-description">
					<legend class="personalized-page__step-title" id="personalized-step-one-title" tabindex="-1"><?php echo esc_html( sarafatto_theme_label( 'Da cosa partiamo?', 'Where shall we start?' ) ); ?></legend>
					<p class="personalized-page__step-description" id="personalized-step-one-description"><?php echo esc_html( sarafatto_theme_label( 'Scegli il prodotto che vorresti personalizzare.', 'Choose the product you would like to personalise.' ) ); ?></p>
					<div class="personalized-page__product-options" role="group" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Prodotto da personalizzare', 'Product to personalise' ) ); ?>">
						<?php foreach ( $product_options as $product_key => $product_label ) : ?>
							<label class="personalized-page__product-option">
								<input type="radio" name="personalized_product" value="<?php echo esc_attr( $product_key ); ?>" required aria-describedby="personalized-product-error">
								<span><?php echo esc_html( $product_label ); ?></span>
							</label>
						<?php endforeach; ?>
					</div>
					<p class="personalized-page__field-error" id="personalized-product-error" data-field-error="personalized_product" role="alert" hidden></p>
					<p class="personalized-page__availability-note"><?php echo esc_html( sarafatto_theme_label( 'La scelta indica una richiesta: Sara verificherà la disponibilità del prodotto e la possibilità di personalizzarlo.', 'Your selection is a request: Sara will check product availability and whether it can be personalised.' ) ); ?></p>
					<p class="personalized-page__field personalized-page__other-product" data-other-product hidden><label for="personalized-other-product"><?php echo esc_html( sarafatto_theme_label( 'Quale prodotto hai in mente? *', 'Which product do you have in mind? *' ) ); ?></label><input id="personalized-other-product" name="personalized_other_product" type="text" maxlength="160" aria-describedby="personalized-other-product-error"><span class="personalized-page__field-error" id="personalized-other-product-error" data-field-error="personalized_other_product" role="alert" hidden></span></p>
					<div class="personalized-page__form-actions">
						<span aria-hidden="true"></span>
						<button class="personalized-page__submit" type="button" data-request-next hidden><?php echo esc_html( sarafatto_theme_label( 'Continua', 'Continue' ) ); ?><span class="icon-[mdi--arrow-right]" aria-hidden="true"></span></button>
					</div>
				</fieldset>

				<fieldset class="personalized-page__step" data-request-step="2" aria-labelledby="personalized-step-two-title" aria-describedby="personalized-step-two-description">
					<legend class="personalized-page__step-title" id="personalized-step-two-title" tabindex="-1"><?php echo esc_html( sarafatto_theme_label( 'Cosa vorresti scrivere?', 'What would you like to write?' ) ); ?></legend>
					<p class="personalized-page__step-description" id="personalized-step-two-description"><?php echo esc_html( sarafatto_theme_label( 'Raccontaci la frase, il nome o la dedica che hai in mente.', 'Tell us the phrase, name or dedication you have in mind.' ) ); ?></p>
					<div class="personalized-page__form-grid">
						<p class="personalized-page__field personalized-page__field--wide"><label for="personalized-text"><?php echo esc_html( sarafatto_theme_label( 'Testo esatto da personalizzare *', 'Exact text to personalise *' ) ); ?></label><textarea id="personalized-text" name="personalized_text" rows="4" maxlength="1500" required aria-describedby="personalized-text-help personalized-text-error"></textarea><span class="personalized-page__field-help" id="personalized-text-help"><?php echo esc_html( sarafatto_theme_label( 'Puoi andare a capo come vuoi che appaia la scritta.', 'Use line breaks to show how you would like the text laid out.' ) ); ?></span><span class="personalized-page__field-error" id="personalized-text-error" data-field-error="personalized_text" role="alert" hidden></span></p>
						<p class="personalized-page__field"><label for="personalized-font"><?php echo esc_html( sarafatto_theme_label( 'Preferenza sul carattere (facoltativa)', 'Font preference (optional)' ) ); ?></label><input id="personalized-font" name="personalized_font" type="text" maxlength="120" placeholder="<?php echo esc_attr( sarafatto_theme_label( 'Es. semplice, corsivo…', 'E.g. simple, script…' ) ); ?>"></p>
						<p class="personalized-page__field"><label for="personalized-color"><?php echo esc_html( sarafatto_theme_label( 'Preferenza sul colore della scritta (facoltativa)', 'Text colour preference (optional)' ) ); ?></label><input id="personalized-color" name="personalized_color" type="text" maxlength="120" placeholder="<?php echo esc_attr( sarafatto_theme_label( 'Descrivi il colore che immagini', 'Describe the colour you have in mind' ) ); ?>"></p>
						<p class="personalized-page__field personalized-page__field--wide"><label for="personalized-style-notes"><?php echo esc_html( sarafatto_theme_label( 'Altre indicazioni sullo stile (facoltative)', 'Other style notes (optional)' ) ); ?></label><textarea id="personalized-style-notes" name="personalized_style_notes" rows="2" maxlength="1000"></textarea></p>
					</div>
					<div class="personalized-page__form-actions">
						<button class="personalized-page__back" type="button" data-request-back hidden><?php echo esc_html( sarafatto_theme_label( 'Indietro', 'Back' ) ); ?></button>
						<button class="personalized-page__submit" type="button" data-request-next hidden><?php echo esc_html( sarafatto_theme_label( 'Continua', 'Continue' ) ); ?><span class="icon-[mdi--arrow-right]" aria-hidden="true"></span></button>
					</div>
				</fieldset>

				<fieldset class="personalized-page__step" data-request-step="3" aria-labelledby="personalized-step-three-title" aria-describedby="personalized-step-three-description">
					<legend class="personalized-page__step-title" id="personalized-step-three-title" tabindex="-1"><?php echo esc_html( sarafatto_theme_label( 'Ultimi dettagli e ci siamo!', 'Just a few last details!' ) ); ?></legend>
					<p class="personalized-page__step-description" id="personalized-step-three-description"><?php echo esc_html( sarafatto_theme_label( 'Lasciaci un recapito: ti ricontatteremo per confermare cosa è possibile realizzare.', 'Leave your contact details so we can confirm what is possible.' ) ); ?></p>
					<div class="personalized-page__form-grid">
						<p class="personalized-page__field"><label for="personalized-quantity"><?php echo esc_html( sarafatto_theme_label( 'Quantità desiderata *', 'Quantity *' ) ); ?></label><input id="personalized-quantity" name="personalized_quantity" type="number" min="1" max="999" value="1" required aria-describedby="personalized-quantity-error"><span class="personalized-page__field-error" id="personalized-quantity-error" data-field-error="personalized_quantity" role="alert" hidden></span></p>
						<p class="personalized-page__field"><label for="personalized-needed-by"><?php echo esc_html( sarafatto_theme_label( 'Entro quando ti serve? (facoltativo)', 'When do you need it by? (optional)' ) ); ?></label><input id="personalized-needed-by" name="personalized_needed_by" type="date"></p>
						<p class="personalized-page__field"><label for="personalized-name"><?php echo esc_html( sarafatto_theme_label( 'Nome *', 'Name *' ) ); ?></label><input id="personalized-name" name="personalized_name" type="text" autocomplete="name" maxlength="120" required aria-describedby="personalized-name-error"><span class="personalized-page__field-error" id="personalized-name-error" data-field-error="personalized_name" role="alert" hidden></span></p>
						<p class="personalized-page__field"><label for="personalized-email"><?php echo esc_html( sarafatto_theme_label( 'Email *', 'Email *' ) ); ?></label><input id="personalized-email" name="personalized_email" type="email" autocomplete="email" maxlength="254" required aria-describedby="personalized-email-error"><span class="personalized-page__field-error" id="personalized-email-error" data-field-error="personalized_email" role="alert" hidden></span></p>
						<p class="personalized-page__field"><label for="personalized-phone"><?php echo esc_html( sarafatto_theme_label( 'Telefono / WhatsApp (facoltativo)', 'Phone / WhatsApp (optional)' ) ); ?></label><input id="personalized-phone" name="personalized_phone" type="tel" autocomplete="tel" maxlength="40"></p>
						<p class="personalized-page__field personalized-page__field--wide"><label for="personalized-notes"><?php echo esc_html( sarafatto_theme_label( 'Note aggiuntive (facoltative)', 'Additional notes (optional)' ) ); ?></label><textarea id="personalized-notes" name="personalized_notes" rows="3" maxlength="2000"></textarea></p>
					</div>
					<section class="personalized-page__summary" aria-labelledby="personalized-summary-title" hidden>
						<h4 id="personalized-summary-title"><?php echo esc_html( sarafatto_theme_label( 'Riepilogo della richiesta', 'Request summary' ) ); ?></h4>
						<article><div class="personalized-page__summary-heading"><h5><?php echo esc_html( sarafatto_theme_label( 'Prodotto', 'Product' ) ); ?></h5><button type="button" data-edit-step="1" hidden><?php echo esc_html( sarafatto_theme_label( 'Modifica', 'Edit' ) ); ?></button></div><dl><dt><?php echo esc_html( sarafatto_theme_label( 'Scelta', 'Selection' ) ); ?></dt><dd data-summary="product"></dd><dt><?php echo esc_html( sarafatto_theme_label( 'Altro prodotto', 'Other product' ) ); ?></dt><dd data-summary="other_product"></dd></dl></article>
						<article><div class="personalized-page__summary-heading"><h5><?php echo esc_html( sarafatto_theme_label( 'Scritta e stile', 'Text and style' ) ); ?></h5><button type="button" data-edit-step="2" hidden><?php echo esc_html( sarafatto_theme_label( 'Modifica', 'Edit' ) ); ?></button></div><dl><dt><?php echo esc_html( sarafatto_theme_label( 'Testo', 'Text' ) ); ?></dt><dd data-summary="text"></dd><dt><?php echo esc_html( sarafatto_theme_label( 'Carattere', 'Font' ) ); ?></dt><dd data-summary="font"></dd><dt><?php echo esc_html( sarafatto_theme_label( 'Colore', 'Colour' ) ); ?></dt><dd data-summary="color"></dd><dt><?php echo esc_html( sarafatto_theme_label( 'Indicazioni', 'Notes' ) ); ?></dt><dd data-summary="style_notes"></dd></dl></article>
						<article><div class="personalized-page__summary-heading"><h5><?php echo esc_html( sarafatto_theme_label( 'Dettagli e contatti', 'Details and contact' ) ); ?></h5></div><dl><dt><?php echo esc_html( sarafatto_theme_label( 'Quantità', 'Quantity' ) ); ?></dt><dd data-summary="quantity"></dd><dt><?php echo esc_html( sarafatto_theme_label( 'Data richiesta', 'Needed by' ) ); ?></dt><dd data-summary="needed_by"></dd><dt><?php echo esc_html( sarafatto_theme_label( 'Nome', 'Name' ) ); ?></dt><dd data-summary="name"></dd><dt>Email</dt><dd data-summary="email"></dd><dt><?php echo esc_html( sarafatto_theme_label( 'Telefono', 'Phone' ) ); ?></dt><dd data-summary="phone"></dd><dt><?php echo esc_html( sarafatto_theme_label( 'Note aggiuntive', 'Additional notes' ) ); ?></dt><dd data-summary="notes"></dd></dl></article>
					</section>
					<p class="personalized-page__privacy"><input id="personalized-privacy" name="personalized_privacy" type="checkbox" value="1" required aria-describedby="personalized-privacy-error"><label for="personalized-privacy"><?php echo esc_html( sarafatto_theme_label( 'Ho letto e accetto l’informativa privacy *', 'I have read and accept the privacy notice *' ) ); ?><?php if ( $privacy_url ) : ?> <a href="<?php echo esc_url( $privacy_url ); ?>" target="_blank" rel="noopener noreferrer"><?php echo esc_html( sarafatto_theme_label( 'Leggila qui', 'Read it here' ) ); ?></a><?php endif; ?></label></p>
						<p class="personalized-page__field-error" id="personalized-privacy-error" data-field-error="personalized_privacy" role="alert" hidden></p>
					<p class="personalized-page__submission-note"><?php echo esc_html( sarafatto_theme_label( 'La richiesta non è un ordine. Ti ricontatteremo per confermare disponibilità, possibilità di personalizzazione, prezzo e tempi.', 'This request is not an order. We’ll contact you to confirm availability, personalisation options, price and timing.' ) ); ?></p>
					<p class="personalized-page__submit-status" data-submit-status role="status" aria-live="polite" hidden><?php echo esc_html( sarafatto_theme_label( 'Invio della richiesta in corso…', 'Sending your request…' ) ); ?></p>
					<div class="personalized-page__form-actions">
						<button class="personalized-page__back" type="button" data-request-back hidden><?php echo esc_html( sarafatto_theme_label( 'Indietro', 'Back' ) ); ?></button>
						<button class="personalized-page__submit" type="submit" data-submit-request><?php echo esc_html( sarafatto_theme_label( 'Invia la tua richiesta', 'Send your request' ) ); ?><span class="icon-[mdi--arrow-right]" aria-hidden="true"></span></button>
					</div>
				</fieldset>
			</form>
		</div>
	</section>

	<section class="personalized-page__reasons" aria-labelledby="personalized-reasons-title">
		<div class="container personalized-page__container">
			<h2 id="personalized-reasons-title"><?php echo esc_html( sarafatto_theme_label( 'Perché scegliere un personalizzato?', 'Why choose a personalised item?' ) ); ?></h2>
			<div class="personalized-page__reasons-grid">
				<?php foreach ( $reasons as $reason ) : ?><article><span class="personalized-page__reason-icon" aria-hidden="true"><span class="<?php echo esc_attr( $reason['icon'] ); ?>"></span></span><h3><?php echo esc_html( $reason['title'] ); ?></h3><p><?php echo esc_html( $reason['copy'] ); ?></p></article><?php endforeach; ?>
			</div>
		</div>
	</section>

	<section class="personalized-page__cta" aria-labelledby="personalized-cta-title">
		<div class="container personalized-page__cta-inner">
			<div class="personalized-page__cta-copy">
				<h2 id="personalized-cta-title"><?php echo esc_html( sarafatto_theme_label( 'Hai già un’idea?', 'Already have an idea?' ) ); ?></h2>
				<p><?php echo esc_html( sarafatto_theme_label( 'Raccontacela: penseremo noi a come realizzarla al meglio.', 'Tell us about it: we’ll help you find the best way to bring it to life.' ) ); ?></p>
				<?php get_template_part( 'template-parts/components/button', null, array( 'label' => sarafatto_theme_label( 'Richiedi il tuo personalizzato', 'Request your personalised item' ), 'href' => '#contatti-form', 'variant' => 'primary', 'size' => 'lg', 'trailing_icon' => 'arrow-right', 'class' => 'personalized-page__cta-button' ) ); ?>
			</div>
			<img src="<?php echo esc_url( $final_banner_image ); ?>" alt="" loading="lazy" decoding="async" />
		</div>
	</section>
</main>
