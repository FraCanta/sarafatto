<?php
/** Accessible contact form handling for the linked Contact page. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Return the current-language Contact URL for post/redirect/get submissions. */
function sarafatto_contact_page_url() {
	$page = function_exists( 'sarafatto_get_linked_page' ) ? sarafatto_get_linked_page( 'contatti' ) : null;
	$url  = $page instanceof WP_Post ? get_permalink( $page ) : '';

	return $url ? $url : home_url( '/contatti/' );
}

/** Validate and send a single contact form message, without retaining submitted personal data. */
function sarafatto_handle_contact_form_submission() {
	$redirect_to = isset( $_POST['redirect_to'] ) ? esc_url_raw( wp_unslash( $_POST['redirect_to'] ) ) : '';
	$redirect_to = wp_validate_redirect( $redirect_to, sarafatto_contact_page_url() );
	$redirect_to = remove_query_arg( 'contact_status', $redirect_to );

	$redirect_with_status = static function ( $status ) use ( $redirect_to ) {
		$target = add_query_arg( 'contact_status', sanitize_key( $status ), $redirect_to );
		$target = preg_replace( '/#.*$/', '', $target );
		wp_safe_redirect( $target . '#contatti-form' );
		exit;
	};

	$nonce = isset( $_POST['sarafatto_contact_nonce'] ) ? sanitize_text_field( wp_unslash( $_POST['sarafatto_contact_nonce'] ) ) : '';
	if ( ! $nonce || ! wp_verify_nonce( $nonce, 'sarafatto_contact_form' ) ) {
		$redirect_with_status( 'invalid' );
	}

	$honeypot = isset( $_POST['contact_website'] ) ? trim( (string) wp_unslash( $_POST['contact_website'] ) ) : '';
	if ( '' !== $honeypot ) {
		$redirect_with_status( 'sent' );
	}

	$name    = isset( $_POST['contact_name'] ) ? sanitize_text_field( wp_unslash( $_POST['contact_name'] ) ) : '';
	$email   = isset( $_POST['contact_email'] ) ? sanitize_email( wp_unslash( $_POST['contact_email'] ) ) : '';
	$phone   = isset( $_POST['contact_phone'] ) ? sanitize_text_field( wp_unslash( $_POST['contact_phone'] ) ) : '';
	$subject = isset( $_POST['contact_subject'] ) ? sanitize_text_field( wp_unslash( $_POST['contact_subject'] ) ) : '';
	$message = isset( $_POST['contact_message'] ) ? sanitize_textarea_field( wp_unslash( $_POST['contact_message'] ) ) : '';
	$product = isset( $_POST['contact_product'] ) ? sanitize_text_field( wp_unslash( $_POST['contact_product'] ) ) : '';
	$phrase  = isset( $_POST['contact_phrase'] ) ? sanitize_text_field( wp_unslash( $_POST['contact_phrase'] ) ) : '';
	$occasion = isset( $_POST['contact_occasion'] ) ? sanitize_text_field( wp_unslash( $_POST['contact_occasion'] ) ) : '';
	$details = isset( $_POST['contact_details'] ) ? sanitize_text_field( wp_unslash( $_POST['contact_details'] ) ) : '';
	$privacy = isset( $_POST['contact_privacy'] ) && '1' === sanitize_text_field( wp_unslash( $_POST['contact_privacy'] ) );

	if ( '' === $name || ! is_email( $email ) || '' === $subject || '' === $message || ! $privacy ) {
		$redirect_with_status( 'invalid' );
	}

	$recipient = function_exists( 'sarafatto_get_setting' ) ? sanitize_email( sarafatto_get_setting( 'email', '' ) ) : '';
	if ( ! is_email( $recipient ) ) {
		$recipient = sanitize_email( get_option( 'admin_email' ) );
	}
	if ( ! is_email( $recipient ) ) {
		$redirect_with_status( 'error' );
	}

	$body = implode(
		"\n",
		array_filter(
			array(
				sprintf( "Nome: %s", $name ),
				sprintf( "Email: %s", $email ),
				'' !== $phone ? sprintf( "Telefono: %s", $phone ) : '',
				'' !== $product ? sprintf( "Prodotto: %s", $product ) : '',
				'' !== $phrase ? sprintf( "Testo o frase: %s", $phrase ) : '',
				'' !== $occasion ? sprintf( "Occasione: %s", $occasion ) : '',
				'' !== $details ? sprintf( "Altre indicazioni: %s", $details ) : '',
				sprintf( "\nMessaggio:\n%s", $message ),
			),
			static function ( $line ) { return '' !== $line; }
		)
	);
	$headers = array( 'Reply-To: ' . $name . ' <' . $email . '>' );
	$sent    = wp_mail( $recipient, '[SaràFatto] ' . $subject, $body, $headers );

	$redirect_with_status( $sent ? 'sent' : 'error' );
}
add_action( 'admin_post_nopriv_sarafatto_contact_submit', 'sarafatto_handle_contact_form_submission' );
add_action( 'admin_post_sarafatto_contact_submit', 'sarafatto_handle_contact_form_submission' );
