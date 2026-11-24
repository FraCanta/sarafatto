<?php
/** Personalised-product request options and submission handler. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Return the product types offered by the request form. Site owners can filter this list. */
function sarafatto_personalized_request_product_options() {
	$options = array(
		'tshirt'     => sarafatto_theme_label( 'T-shirt', 'T-shirt' ),
		'sweatshirt' => sarafatto_theme_label( 'Felpa', 'Sweatshirt' ),
		'tote_bag'   => sarafatto_theme_label( 'Shopper / tote bag', 'Shopper / tote bag' ),
		'pouch'      => sarafatto_theme_label( 'Pochette', 'Pouch' ),
		'other'      => sarafatto_theme_label( 'Altro', 'Other' ),
		'advice'     => sarafatto_theme_label( 'Non so ancora, vorrei un consiglio', 'I’m not sure yet; I’d like advice' ),
	);

	/**
	 * Filter the product types displayed and accepted by the request form.
	 * Return an associative array of stable keys and translated labels.
	 */
	$options = apply_filters( 'sarafatto_personalized_request_product_options', $options );

	if ( ! is_array( $options ) ) {
		return array();
	}

	$clean_options = array();
	foreach ( $options as $key => $label ) {
		if ( is_string( $key ) && preg_match( '/^[a-z0-9_]+$/', $key ) && is_scalar( $label ) && '' !== trim( (string) $label ) ) {
			$clean_options[ $key ] = sanitize_text_field( (string) $label );
		}
	}

	return $clean_options;
}

/** Redirect a personalised request with a generic status and no personal data in the URL. */
function sarafatto_personalized_request_redirect( $status, $redirect_to ) {
	$fallback = home_url( '/personalizzati/' );
	$target   = wp_validate_redirect( $redirect_to, $fallback );
	$target   = remove_query_arg( 'personalized_request_status', $target );
	$target   = preg_replace( '/#.*$/', '', $target );
	wp_safe_redirect( add_query_arg( 'personalized_request_status', sanitize_key( $status ), $target ) . '#contatti-form' );
	exit;
}

/** Validate and email a personalised-product request without retaining the submitted details. */
function sarafatto_handle_personalized_request_submission() {
	$redirect_to = isset( $_POST['personalized_redirect_to'] ) && is_string( $_POST['personalized_redirect_to'] ) ? esc_url_raw( wp_unslash( $_POST['personalized_redirect_to'] ) ) : '';
	$nonce       = isset( $_POST['personalized_nonce'] ) && is_string( $_POST['personalized_nonce'] ) ? sanitize_text_field( wp_unslash( $_POST['personalized_nonce'] ) ) : '';
	if ( ! $nonce || ! wp_verify_nonce( $nonce, 'sarafatto_personalized_request' ) ) {
		sarafatto_personalized_request_redirect( 'invalid', $redirect_to );
	}

	$honeypot = isset( $_POST['personalized_website'] ) && is_string( $_POST['personalized_website'] ) ? trim( (string) wp_unslash( $_POST['personalized_website'] ) ) : '';
	if ( '' !== $honeypot ) {
		sarafatto_personalized_request_redirect( 'error', $redirect_to );
	}

	$options = sarafatto_personalized_request_product_options();
	$product = isset( $_POST['personalized_product'] ) && is_string( $_POST['personalized_product'] ) ? sanitize_key( wp_unslash( $_POST['personalized_product'] ) ) : '';
	$other_product = isset( $_POST['personalized_other_product'] ) && is_string( $_POST['personalized_other_product'] ) ? sanitize_text_field( wp_unslash( $_POST['personalized_other_product'] ) ) : '';
	$text = isset( $_POST['personalized_text'] ) && is_string( $_POST['personalized_text'] ) ? sanitize_textarea_field( wp_unslash( $_POST['personalized_text'] ) ) : '';
	$font = isset( $_POST['personalized_font'] ) && is_string( $_POST['personalized_font'] ) ? sanitize_text_field( wp_unslash( $_POST['personalized_font'] ) ) : '';
	$color = isset( $_POST['personalized_color'] ) && is_string( $_POST['personalized_color'] ) ? sanitize_text_field( wp_unslash( $_POST['personalized_color'] ) ) : '';
	$style_notes = isset( $_POST['personalized_style_notes'] ) && is_string( $_POST['personalized_style_notes'] ) ? sanitize_textarea_field( wp_unslash( $_POST['personalized_style_notes'] ) ) : '';
	$quantity = isset( $_POST['personalized_quantity'] ) && is_scalar( $_POST['personalized_quantity'] ) ? absint( (string) wp_unslash( $_POST['personalized_quantity'] ) ) : 0;
	$needed_by = isset( $_POST['personalized_needed_by'] ) && is_string( $_POST['personalized_needed_by'] ) ? sanitize_text_field( wp_unslash( $_POST['personalized_needed_by'] ) ) : '';
	$name = isset( $_POST['personalized_name'] ) && is_string( $_POST['personalized_name'] ) ? sanitize_text_field( wp_unslash( $_POST['personalized_name'] ) ) : '';
	$email = isset( $_POST['personalized_email'] ) && is_string( $_POST['personalized_email'] ) ? sanitize_email( wp_unslash( $_POST['personalized_email'] ) ) : '';
	$phone = isset( $_POST['personalized_phone'] ) && is_string( $_POST['personalized_phone'] ) ? sanitize_text_field( wp_unslash( $_POST['personalized_phone'] ) ) : '';
	$notes = isset( $_POST['personalized_notes'] ) && is_string( $_POST['personalized_notes'] ) ? sanitize_textarea_field( wp_unslash( $_POST['personalized_notes'] ) ) : '';
	$privacy = isset( $_POST['personalized_privacy'] ) && is_scalar( $_POST['personalized_privacy'] ) && '1' === sanitize_text_field( (string) wp_unslash( $_POST['personalized_privacy'] ) );

	$date_is_valid = '' === $needed_by;
	if ( '' !== $needed_by ) {
		$date = DateTime::createFromFormat( '!Y-m-d', $needed_by );
		$date_is_valid = $date instanceof DateTime && $date->format( 'Y-m-d' ) === $needed_by;
	}

	if (
		! isset( $options[ $product ] )
		|| ( 'other' === $product && '' === $other_product )
		|| '' === $text
		|| $quantity < 1
		|| $quantity > 999
		|| ! $date_is_valid
		|| '' === $name
		|| ! is_email( $email )
		|| ! $privacy
	) {
		sarafatto_personalized_request_redirect( 'invalid', $redirect_to );
	}

	$remote_ip = isset( $_SERVER['REMOTE_ADDR'] ) && is_string( $_SERVER['REMOTE_ADDR'] ) ? sanitize_text_field( wp_unslash( $_SERVER['REMOTE_ADDR'] ) ) : '';
	if ( '' !== $remote_ip ) {
		$limit_key = 'sarafatto_personalized_request_' . hash_hmac( 'sha256', $remote_ip, wp_salt( 'auth' ) );
		$requests  = absint( get_transient( $limit_key ) );
		if ( $requests >= 4 ) {
			sarafatto_personalized_request_redirect( 'rate_limited', $redirect_to );
		}
		set_transient( $limit_key, $requests + 1, 15 * MINUTE_IN_SECONDS );
	}

	$recipient = function_exists( 'sarafatto_get_setting' ) ? sanitize_email( sarafatto_get_setting( 'email', '' ) ) : '';
	if ( ! is_email( $recipient ) ) {
		$recipient = sanitize_email( get_option( 'admin_email' ) );
	}
	$recipient = apply_filters( 'sarafatto_personalized_request_recipient', $recipient );
	$recipient = is_string( $recipient ) ? sanitize_email( $recipient ) : '';
	if ( ! is_email( $recipient ) ) {
		sarafatto_personalized_request_redirect( 'error', $redirect_to );
	}

	$product_label = $options[ $product ];
	if ( 'other' === $product ) {
		$product_label .= ' — ' . $other_product;
	}

	$body_lines = array(
		sprintf( 'Prodotto richiesto: %s', $product_label ),
		sprintf( "Scritta esatta:\n%s", $text ),
		sprintf( 'Preferenza carattere: %s', '' !== $font ? $font : 'Nessuna indicata' ),
		sprintf( 'Preferenza colore: %s', '' !== $color ? $color : 'Nessuna indicata' ),
		sprintf( "Altre indicazioni sullo stile:\n%s", '' !== $style_notes ? $style_notes : 'Nessuna indicata' ),
		sprintf( 'Quantità: %d', $quantity ),
		sprintf( 'Data entro cui serve: %s', '' !== $needed_by ? $needed_by : 'Non indicata' ),
		sprintf( 'Nome: %s', $name ),
		sprintf( 'Email: %s', $email ),
		'' !== $phone ? sprintf( 'Telefono/WhatsApp: %s', $phone ) : 'Telefono/WhatsApp: Non indicato',
		sprintf( "Note aggiuntive:\n%s", '' !== $notes ? $notes : 'Nessuna' ),
		'',
		'La richiesta non è un ordine. Contattare la persona per confermare disponibilità, possibilità di personalizzazione, prezzo e tempi.',
	);
	$headers = array( 'Reply-To: ' . $name . ' <' . $email . '>' );
	$sent    = wp_mail( $recipient, '[SaràFatto] Richiesta di personalizzazione', implode( "\n\n", $body_lines ), $headers );

	sarafatto_personalized_request_redirect( $sent ? 'sent' : 'error', $redirect_to );
}
add_action( 'admin_post_nopriv_sarafatto_personalized_request_submit', 'sarafatto_handle_personalized_request_submission' );
add_action( 'admin_post_sarafatto_personalized_request_submit', 'sarafatto_handle_personalized_request_submission' );
