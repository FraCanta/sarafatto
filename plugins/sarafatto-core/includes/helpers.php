<?php
/** Shared accessors for the Saràfatto settings option. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Return a setting value, or the supplied fallback when it is not configured.
 *
 * @param string $key     Setting key.
 * @param mixed  $default Fallback value.
 * @return mixed
 */
function sarafatto_get_setting( $key, $default = '' ) {
	$key      = is_string( $key ) ? sanitize_key( $key ) : '';
	$settings = get_option( 'sarafatto_settings', array() );
	if ( ! is_array( $settings ) || ! array_key_exists( $key, $settings ) ) {
		return $default;
	}

	$value = is_scalar( $settings[ $key ] ) ? $settings[ $key ] : $default;
	$translatable_keys = array( 'orari', 'whatsapp_message', 'shipping_title', 'shipping_text', 'shipping_zone' );
	if ( is_string( $value ) && in_array( $key, $translatable_keys, true ) && function_exists( 'pll__' ) ) {
		return pll__( $value );
	}

	return $value;
}

/** Return the currently configured static front page ID, or zero. */
function sarafatto_get_front_page_id() {
	if ( 'page' !== get_option( 'show_on_front' ) ) {
		return 0;
	}

	return absint( get_option( 'page_on_front' ) );
}

/**
 * Return the ID of a page connected to a known content role.
 *
 * @param string $role Page role key.
 * @return int
 */
function sarafatto_get_linked_page_id( $role ) {
	$roles = array( 'negozio', 'idee_regalo', 'personalizzati', 'spedizioni', 'contatti' );
	if ( ! in_array( $role, $roles, true ) ) {
		return 0;
	}

	$page_id = absint( sarafatto_get_setting( 'page_' . $role, 0 ) );
	if ( $page_id && function_exists( 'pll_current_language' ) && function_exists( 'pll_get_post' ) ) {
		$page_id = sarafatto_get_translation_id( $page_id, 'post', sarafatto_get_current_language() );
	}

	return $page_id;
}

/**
 * Return the published page connected to a known content role.
 *
 * @param string $role Page role key.
 * @return WP_Post|null
 */
function sarafatto_get_linked_page( $role ) {
	$page_id = sarafatto_get_linked_page_id( $role );
	$page    = $page_id ? get_post( $page_id ) : null;

	if ( ! $page instanceof WP_Post || 'page' !== $page->post_type || 'publish' !== $page->post_status ) {
		return null;
	}

	return $page;
}

/**
 * Build a WhatsApp URL using the configured phone number and message.
 *
 * Passing a message allows future callers to compose a message around a post title.
 *
 * @param string $message Optional message override.
 * @return string Sanitized URL, or an empty string when no number is configured.
 */
function sarafatto_get_whatsapp_url( $message = '' ) {
	$phone_setting = sarafatto_get_setting( 'whatsapp', '' );
	$phone         = is_scalar( $phone_setting ) ? preg_replace( '/\D+/', '', (string) $phone_setting ) : '';
	if ( ! $phone ) {
		return '';
	}

	$message = is_scalar( $message ) ? (string) $message : '';
	$message = '' !== trim( $message ) ? $message : sarafatto_get_setting( 'whatsapp_message', '' );
	$url     = 'https://wa.me/' . $phone;
	if ( '' !== trim( (string) $message ) ) {
		$url = add_query_arg( 'text', (string) $message, $url );
	}

	return esc_url_raw( $url );
}

/** Validate a strict YYYY-MM-DD date using the configured WordPress timezone. */
function sarafatto_is_valid_calendar_date( $value ) {
	if ( ! is_string( $value ) || ! preg_match( '/^\d{4}-\d{2}-\d{2}$/', $value ) ) {
		return false;
	}

	$date   = DateTimeImmutable::createFromFormat( '!Y-m-d', $value, wp_timezone() );
	$errors = DateTimeImmutable::getLastErrors();

	return $date instanceof DateTimeImmutable
		&& ( false === $errors || ( 0 === $errors['warning_count'] && 0 === $errors['error_count'] ) )
		&& $date->format( 'Y-m-d' ) === $value;
}

/** Check whether a term occasion is active today, with inclusive boundaries. */
function sarafatto_is_occasion_active( $term_id ) {
	$term = get_term( absint( $term_id ), 'sarafatto_occasione' );
	if ( ! $term instanceof WP_Term ) {
		return false;
	}

	$start_date = get_term_meta( $term->term_id, 'sarafatto_occasion_start_date', true );
	$end_date   = get_term_meta( $term->term_id, 'sarafatto_occasion_end_date', true );
	if ( ! sarafatto_is_valid_calendar_date( $start_date ) || ! sarafatto_is_valid_calendar_date( $end_date ) || $start_date > $end_date ) {
		return false;
	}

	$today = current_datetime()->format( 'Y-m-d' );
	return $today >= $start_date && $today <= $end_date;
}

/** Return all currently active occasions for future theme queries. */
function sarafatto_get_active_occasions() {
	$terms = get_terms(
		sarafatto_add_language_to_query_args( array(
			'taxonomy'   => 'sarafatto_occasione',
			'hide_empty' => false,
			'orderby'    => 'name',
			'order'      => 'ASC',
		) )
	);
	if ( is_wp_error( $terms ) ) {
		return array();
	}

	return array_values(
		array_filter(
			$terms,
			static function ( $term ) {
				return $term instanceof WP_Term && sarafatto_is_occasion_active( $term->term_id );
			}
		)
	);
}

/** Return the two editorial flags for a product; both default to false. */
function sarafatto_get_product_flags( $post_id ) {
	$product = get_post( absint( $post_id ) );
	if ( ! $product instanceof WP_Post || 'sarafatto_prodotto' !== $product->post_type ) {
		return array( 'is_new' => false, 'is_featured' => false );
	}

	return array(
		'is_new'      => '1' === (string) get_post_meta( $product->ID, 'sarafatto_is_new', true ),
		'is_featured' => '1' === (string) get_post_meta( $product->ID, 'sarafatto_is_featured', true ),
	);
}
