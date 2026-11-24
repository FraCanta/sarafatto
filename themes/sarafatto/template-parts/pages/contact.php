<?php
/** Contact landing page with editorial hero, map, contact form and FAQ. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$get_setting = static function ( $key ) {
	return function_exists( 'sarafatto_get_setting' ) ? sarafatto_get_setting( $key, '' ) : '';
};
$email       = sanitize_email( $get_setting( 'email' ) );
$whatsapp_phone_value = $get_setting( 'whatsapp' );
$whatsapp_phone = is_scalar( $whatsapp_phone_value ) ? trim( (string) $whatsapp_phone_value ) : '';
$address_value = $get_setting( 'indirizzo' );
$address     = is_scalar( $address_value ) ? trim( (string) $address_value ) : '';
$hours_value = $get_setting( 'orari' );
$hours       = is_scalar( $hours_value ) ? trim( (string) $hours_value ) : '';
$whatsapp_url = function_exists( 'sarafatto_get_whatsapp_url' ) ? sarafatto_get_whatsapp_url() : '';
$personalized_page_id = function_exists( 'sarafatto_get_linked_page_id' ) ? sarafatto_get_linked_page_id( 'personalizzati' ) : 0;
$personalized_url = $personalized_page_id ? get_permalink( $personalized_page_id ) : '';
$privacy_url = function_exists( 'get_privacy_policy_url' ) ? get_privacy_policy_url() : '';
$status      = isset( $_GET['contact_status'] ) ? sanitize_key( wp_unslash( $_GET['contact_status'] ) ) : ''; // phpcs:ignore WordPress.Security.NonceVerification.Recommended
$status_text = array(
	'sent'    => sarafatto_theme_label( 'Messaggio inviato. Ti risponderò appena possibile.', 'Message sent. I’ll get back to you as soon as possible.' ),
	'invalid' => sarafatto_theme_label( 'Controlla i campi obbligatori e accetta l’informativa privacy.', 'Check the required fields and accept the privacy notice.' ),
	'error'   => sarafatto_theme_label( 'Non è stato possibile inviare il messaggio. Riprova più tardi o scrivimi su WhatsApp.', 'The message could not be sent. Please try again later or contact me on WhatsApp.' ),
);
$contact_title = sarafatto_theme_label( 'CONTATTI', 'CONTACT' );
$contact_intro_first = sarafatto_theme_label( 'Vuoi informazioni o desideri acquistare?', 'Need more information or ready to buy?' );
$map_embed_url = add_query_arg(
	array(
		'bbox'  => '16.0122,41.94605,16.0152,41.94695',
		'layer' => 'mapnik',
	),
	'https://www.openstreetmap.org/export/embed.html'
);
?>
<main id="main-content" class="site-main contact-page" tabindex="-1">
	<section class="contact-page__hero" data-contact-hero aria-labelledby="contact-hero-title">
		<svg class="contact-page__hero-shape" viewBox="0 0 1440 820" preserveAspectRatio="none" aria-hidden="true" focusable="false">
			<path data-contact-curve d="M0 0H1440V680 C1080 840 360 840 0 680Z" />
		</svg>
		<div class="contact-page__hero-content">
			<nav class="contact-page__breadcrumb" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Percorso di navigazione', 'Breadcrumb' ) ); ?>">
				<a href="<?php echo esc_url( function_exists( 'sarafatto_get_language_home_url' ) ? sarafatto_get_language_home_url() : home_url( '/' ) ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Home', 'Home' ) ); ?></a>
				<span aria-hidden="true">›</span>
				<span aria-current="page"><?php echo esc_html( sarafatto_theme_label( 'Contatti', 'Contact' ) ); ?></span>
			</nav>
			<h1 class="contact-page__hero-title" id="contact-hero-title">
				<span class="contact-page__marquee" aria-hidden="true">
					<?php for ( $copy = 0; $copy < 2; $copy++ ) : ?>
						<span class="contact-page__marquee-group">
							<?php for ( $item = 0; $item < 4; $item++ ) : ?>
								<span><?php echo esc_html( $contact_title ); ?></span><span class="contact-page__asterisk" aria-hidden="true">*</span>
							<?php endfor; ?>
						</span>
					<?php endfor; ?>
				</span>
				<span class="screen-reader-text"><?php echo esc_html( $contact_title ); ?></span>
			</h1>
			<p class="contact-page__hero-description"><?php echo esc_html( $contact_intro_first ); ?></p>
			<a class="button button--primary button--lg contact-page__hero-cta" href="#contatti-form">
				<span class="button__label"><?php echo esc_html( sarafatto_theme_label( 'Contattami', 'Contact me' ) ); ?></span>
				<svg class="button__icon button__icon--trailing contact-page__hero-arrow" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 4v15m-7-7 7 7 7-7" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" /></svg>
			</a>
		</div>
	</section>

	<section class="contact-page__map-section" aria-labelledby="contact-map-title">
		<h2 class="screen-reader-text" id="contact-map-title"><?php echo esc_html( sarafatto_theme_label( 'Dove siamo', 'Where we are' ) ); ?></h2>
		<div class="contact-page__map-frame" data-contact-map-frame>
			<iframe
				title="<?php echo esc_attr( sarafatto_theme_label( 'Mappa di Corso Garibaldi 53, Peschici', 'Map of Corso Garibaldi 53, Peschici' ) ); ?>"
				src="<?php echo esc_url( $map_embed_url ); ?>"
				loading="lazy"
				referrerpolicy="strict-origin-when-cross-origin"
				tabindex="-1"
				aria-hidden="true"
			></iframe>
			<span class="contact-page__map-pin" role="img" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'SaràFatto, Corso Garibaldi 53, Peschici', 'SaràFatto, Corso Garibaldi 53, Peschici' ) ); ?>"><span></span></span>
			<span class="contact-page__map-label" aria-hidden="true">SaràFatto</span>
		</div>
	</section>

	<section class="contact-page__details section-shell" aria-labelledby="contact-details-title">
		<div class="contact-page__details-inner container">
			<h2 class="screen-reader-text" id="contact-details-title"><?php echo esc_html( sarafatto_theme_label( 'Contatti e modulo di richiesta', 'Contact details and enquiry form' ) ); ?></h2>
			<div class="contact-page__details-grid">
				<aside class="contact-page__info" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Contatti rapidi', 'Quick contacts' ) ); ?>">
					<?php if ( $whatsapp_url ) : ?>
						<a class="contact-page__info-item" href="<?php echo esc_url( $whatsapp_url ); ?>" target="_blank" rel="noopener noreferrer">
							<span class="contact-page__info-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M20.5 11.7a8.4 8.4 0 0 1-12.4 7.4L3 20.4l1.3-4.8a8.4 8.4 0 1 1 16.2-3.9Z"/><path d="M8.7 8.4c.2-.5.4-.5.7-.5h.5c.2 0 .4.1.5.4l.7 1.7c.1.2.1.4 0 .6l-.5.7c-.2.2-.2.4-.1.6.5.9 1.2 1.6 2.1 2.1.2.1.4.1.6-.1l.8-.9c.2-.2.4-.2.6-.1l1.6.8c.3.1.4.3.4.5 0 .3-.1 1.2-.7 1.7-.6.6-1.4.7-1.8.7-.5 0-1.1-.1-2.6-.8-2.2-1-3.6-3.2-3.8-3.5-.1-.2-.9-1.2-.9-2.3 0-1.1.5-1.6.7-1.8Z"/></svg></span>
							<span class="contact-page__info-copy"><strong>WhatsApp</strong><span><?php echo esc_html( $whatsapp_phone ? $whatsapp_phone : sarafatto_theme_label( 'Scrivimi per informazioni o ordini', 'Message me about products or orders' ) ); ?></span></span>
						</a>
					<?php endif; ?>
					<?php if ( $email ) : ?>
						<a class="contact-page__info-item" href="mailto:<?php echo esc_attr( $email ); ?>">
							<span class="contact-page__info-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="14" rx="2"/><path d="m4.5 7 7.5 6 7.5-6"/></svg></span>
							<span class="contact-page__info-copy"><strong>Email</strong><span><?php echo esc_html( $email ); ?></span></span>
						</a>
					<?php endif; ?>
					<?php if ( $address ) : ?>
						<div class="contact-page__info-item">
							<span class="contact-page__info-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2.3"/></svg></span>
							<span class="contact-page__info-copy"><strong><?php echo esc_html( sarafatto_theme_label( 'Indirizzo', 'Address' ) ); ?></strong><address><?php echo nl2br( esc_html( $address ) ); ?></address></span>
						</div>
					<?php endif; ?>
					<?php if ( $hours ) : ?>
						<div class="contact-page__info-item">
							<span class="contact-page__info-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/></svg></span>
							<span class="contact-page__info-copy"><strong><?php echo esc_html( sarafatto_theme_label( 'Orari di apertura', 'Opening hours' ) ); ?></strong><span><?php echo nl2br( esc_html( $hours ) ); ?></span></span>
						</div>
					<?php endif; ?>
					<div class="contact-page__info-item">
						<span class="contact-page__info-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M20.8 9.3c0 5.1-8.8 11-8.8 11s-8.8-5.9-8.8-11a8.8 8.8 0 1 1 17.6 0Z"/><path d="M8.5 10.2c0-1.8 1.4-3.2 3.2-3.2 1.2 0 2.2.6 2.8 1.6"/><path d="M15.4 13.2c-.5 1.2-1.7 2-3.1 2-1.8 0-3.2-1.4-3.2-3.2"/></svg></span>
						<span class="contact-page__info-copy"><strong><?php echo esc_html( sarafatto_theme_label( 'Personalizzati', 'Personalised' ) ); ?></strong><span><?php echo esc_html( sarafatto_theme_label( 'Vuoi un prodotto unico? Raccontami la tua idea: insieme possiamo creare qualcosa su misura per te.', 'Looking for something unique? Tell me your idea and we can create something just for you.' ) ); ?></span><?php if ( $personalized_url ) : ?><a href="<?php echo esc_url( $personalized_url ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Scopri di più', 'Discover more' ) ); ?></a><?php endif; ?></span>
					</div>
				</aside>

				<section class="contact-page__form-wrap" id="contatti-form" tabindex="-1" aria-labelledby="contact-form-title">
					<h2 class="screen-reader-text" id="contact-form-title"><?php echo esc_html( sarafatto_theme_label( 'Inviami un messaggio', 'Send me a message' ) ); ?></h2>
					<?php if ( isset( $status_text[ $status ] ) ) : ?>
						<p class="contact-page__notice contact-page__notice--<?php echo esc_attr( $status ); ?>" role="status" tabindex="-1" data-contact-status><?php echo esc_html( $status_text[ $status ] ); ?></p>
					<?php endif; ?>
					<form class="contact-page__form" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" method="post">
						<input type="hidden" name="action" value="sarafatto_contact_submit">
						<input type="hidden" name="redirect_to" value="<?php echo esc_url( get_permalink( get_queried_object_id() ) ); ?>">
						<?php wp_nonce_field( 'sarafatto_contact_form', 'sarafatto_contact_nonce' ); ?>
						<div class="contact-page__trap" aria-hidden="true"><label for="contact-website">Website</label><input id="contact-website" type="text" name="contact_website" tabindex="-1" autocomplete="off"></div>
						<div class="contact-page__form-grid">
							<p class="contact-page__field"><label class="screen-reader-text" for="contact-name"><?php echo esc_html( sarafatto_theme_label( 'Nome e cognome', 'Full name' ) ); ?></label><input id="contact-name" name="contact_name" type="text" autocomplete="name" maxlength="120" placeholder="<?php echo esc_attr( sarafatto_theme_label( 'Nome e cognome *', 'Full name *' ) ); ?>" required></p>
							<p class="contact-page__field"><label class="screen-reader-text" for="contact-email">Email</label><input id="contact-email" name="contact_email" type="email" autocomplete="email" maxlength="254" placeholder="Email *" required></p>
							<p class="contact-page__field"><label class="screen-reader-text" for="contact-phone"><?php echo esc_html( sarafatto_theme_label( 'Numero di telefono', 'Phone number' ) ); ?></label><input id="contact-phone" name="contact_phone" type="tel" autocomplete="tel" maxlength="40" placeholder="<?php echo esc_attr( sarafatto_theme_label( 'Numero di telefono', 'Phone number' ) ); ?>"></p>
							<p class="contact-page__field"><label class="screen-reader-text" for="contact-subject"><?php echo esc_html( sarafatto_theme_label( 'Oggetto', 'Subject' ) ); ?></label><select id="contact-subject" name="contact_subject" required><option value=""><?php echo esc_html( sarafatto_theme_label( 'Oggetto *', 'Subject *' ) ); ?></option><option value="<?php echo esc_attr( sarafatto_theme_label( 'Informazioni sui prodotti', 'Product information' ) ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Informazioni sui prodotti', 'Product information' ) ); ?></option><option value="<?php echo esc_attr( sarafatto_theme_label( 'Ordine', 'Order' ) ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Ordine', 'Order' ) ); ?></option><option value="<?php echo esc_attr( sarafatto_theme_label( 'Prodotto personalizzato', 'Personalised product' ) ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Prodotto personalizzato', 'Personalised product' ) ); ?></option><option value="<?php echo esc_attr( sarafatto_theme_label( 'Altro', 'Other' ) ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Altro', 'Other' ) ); ?></option></select></p>
							<p class="contact-page__field contact-page__field--wide"><label class="screen-reader-text" for="contact-message"><?php echo esc_html( sarafatto_theme_label( 'Il tuo messaggio', 'Your message' ) ); ?></label><textarea id="contact-message" name="contact_message" rows="4" maxlength="5000" placeholder="<?php echo esc_attr( sarafatto_theme_label( 'Il tuo messaggio *', 'Your message *' ) ); ?>" required></textarea></p>
						</div>
						<p class="contact-page__privacy"><input id="contact-privacy" name="contact_privacy" type="checkbox" value="1" required><label for="contact-privacy"><?php echo esc_html( sarafatto_theme_label( 'Ho letto e accetto l’informativa privacy', 'I have read and accept the privacy notice' ) ); ?><?php if ( $privacy_url ) : ?> <a href="<?php echo esc_url( $privacy_url ); ?>" target="_blank" rel="noopener noreferrer"><?php echo esc_html( sarafatto_theme_label( 'Leggila qui', 'Read it here' ) ); ?><span class="screen-reader-text"> (<?php echo esc_html( sarafatto_theme_label( 'si apre in una nuova scheda', 'opens in a new tab' ) ); ?>)</span></a><?php endif; ?></label></p>
						<?php
						get_template_part(
							'template-parts/components/button',
							null,
							array(
								'label'   => sarafatto_theme_label( 'Invia messaggio', 'Send message' ),
								'variant' => 'primary',
								'size'    => 'lg',
								'type'    => 'submit',
								'trailing_icon' => 'arrow-right',
								'class'   => 'contact-page__submit',
							)
						);
						?>
					</form>
				</section>
			</div>
		</div>
	</section>

	<section class="contact-page__identity" aria-labelledby="contact-identity-title">
		<div class="contact-page__identity-intro">
			<h2 id="contact-identity-title"><?php echo esc_html( sarafatto_theme_label( 'Prodotti, idee regalo e creazioni personalizzate.', 'Products, gift ideas and personalised creations.' ) ); ?></h2>
			<p><?php echo esc_html( sarafatto_theme_label( 'Raccontami cosa hai in mente: ci pensiamo insieme!', 'Tell me what you have in mind — we’ll think it through together!' ) ); ?></p>
		</div>
		<?php
		get_template_part(
			'template-parts/home/ribbon',
			null,
			array(
				'phrase' => sarafatto_theme_label( 'SARÀ FATTO  ✶  IDEE REGALO  ✶  PERSONALIZZATI  ✶', 'SARÀ FATTO  ✶  GIFT IDEAS  ✶  PERSONALISED  ✶' ),
				'copies' => 5,
			)
		);
		?>
	</section>

	<section class="contact-page__faq section-shell" aria-labelledby="contact-faq-title">
		<div class="contact-page__faq-inner container">
			<header class="contact-page__faq-heading"><h2 id="contact-faq-title"><?php echo esc_html( sarafatto_theme_label( 'Dubbi? Ecco le risposte più comuni.', 'Questions? Here are some common answers.' ) ); ?></h2></header>
			<div class="contact-page__faq-list">
				<details><summary><span class="contact-page__faq-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 8h14l1 12H4L5 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/></svg></span><span class="contact-page__faq-question"><?php echo esc_html( sarafatto_theme_label( 'Come posso effettuare un ordine?', 'How can I place an order?' ) ); ?></span></summary><p><?php echo esc_html( sarafatto_theme_label( 'Scegli i prodotti dal catalogo e completa l’ordine online. Se hai bisogno di aiuto, scrivimi dal modulo o su WhatsApp.', 'Choose products from the catalog and complete your order online. If you need help, use the form or message me on WhatsApp.' ) ); ?></p></details>
				<details><summary><span class="contact-page__faq-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 7h11v11H3zM14 11h4l3 3v4h-7z"/><circle cx="7" cy="19" r="1.8"/><circle cx="18" cy="19" r="1.8"/></svg></span><span class="contact-page__faq-question"><?php echo esc_html( sarafatto_theme_label( 'Spedite anche fuori da Peschici?', 'Do you ship outside Peschici?' ) ); ?></span></summary><p><?php echo esc_html( sarafatto_theme_label( 'Sì, spedisco in Italia e in Europa. Per tempi e costi specifici, scrivimi indicando il prodotto e la destinazione.', 'Yes, I ship across Italy and Europe. For exact timing and costs, send me the product and destination.' ) ); ?></p></details>
				<details><summary><span class="contact-page__faq-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z"/></svg></span><span class="contact-page__faq-question"><?php echo esc_html( sarafatto_theme_label( 'Posso richiedere un prodotto personalizzato?', 'Can I request a personalised product?' ) ); ?></span></summary><p><?php echo esc_html( sarafatto_theme_label( 'Certo. Raccontami la tua idea e il prodotto che vorresti personalizzare: ti risponderò con le possibilità disponibili.', 'Of course. Tell me your idea and which product you would like personalised, and I’ll get back to you with the options.' ) ); ?></p></details>
				<details><summary><span class="contact-page__faq-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/></svg></span><span class="contact-page__faq-question"><?php echo esc_html( sarafatto_theme_label( 'Quali sono i tempi di realizzazione?', 'How long does it take to make?' ) ); ?></span></summary><p><?php echo esc_html( sarafatto_theme_label( 'I tempi variano in base al prodotto e al tipo di personalizzazione. Ti confermerò una stima prima di iniziare.', 'Timing depends on the product and customisation. I’ll confirm an estimate before starting.' ) ); ?></p></details>
			</div>
		</div>
	</section>
</main>
