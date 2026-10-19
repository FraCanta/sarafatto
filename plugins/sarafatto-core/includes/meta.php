<?php
/** Register Product metadata. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function sarafatto_register_post_meta() {
	$product_meta = array(
		'sarafatto_editorial_label' => array( 'string', 'sanitize_text_field' ),
		'sarafatto_is_new'          => array( 'boolean', 'rest_sanitize_boolean' ),
		'sarafatto_is_featured'     => array( 'boolean', 'rest_sanitize_boolean' ),
		'sarafatto_is_sold_out'     => array( 'boolean', 'rest_sanitize_boolean' ),
		'sarafatto_personalizable'  => array( 'boolean', 'rest_sanitize_boolean' ),
		'sarafatto_materials'       => array( 'string', 'sanitize_textarea_field' ),
		'sarafatto_dimensions'      => array( 'string', 'sanitize_textarea_field' ),
		'sarafatto_colors'          => array( 'string', 'sanitize_textarea_field' ),
		'sarafatto_variants'        => array( 'string', 'sanitize_textarea_field' ),
		'sarafatto_care'             => array( 'string', 'sanitize_textarea_field' ),
		'sarafatto_is_handmade'      => array( 'boolean', 'rest_sanitize_boolean' ),
		'sarafatto_customization_details' => array( 'string', 'sanitize_textarea_field' ),
		// Keep the previous key registered so existing saved values remain accessible.
		'sarafatto_personalization_details' => array( 'string', 'sanitize_textarea_field' ),
		'sarafatto_story'           => array( 'string', 'sarafatto_sanitize_story' ),
		'sarafatto_story_title'     => array( 'string', 'sanitize_text_field' ),
		'sarafatto_story_image'     => array( 'integer', 'sarafatto_sanitize_product_image_id' ),
		'sarafatto_gallery'         => array( 'array', 'sarafatto_sanitize_gallery_ids' ),
		'sarafatto_price'           => array( 'string', 'sarafatto_sanitize_price_meta' ),
		'sarafatto_sku'             => array( 'string', 'sarafatto_sanitize_sku' ),
	);

	foreach ( $product_meta as $meta_key => $field ) {
		$meta_args = array(
			'type'              => $field[0],
			'single'            => true,
			'revisions_enabled' => true,
			'sanitize_callback' => $field[1],
			'auth_callback'     => 'sarafatto_can_edit_product_meta',
		);
		if ( in_array( $meta_key, array( 'sarafatto_is_new', 'sarafatto_is_featured', 'sarafatto_is_sold_out', 'sarafatto_personalizable', 'sarafatto_is_handmade' ), true ) ) {
			$meta_args['default'] = false;
		}
		register_post_meta( 'sarafatto_prodotto', $meta_key, $meta_args );
	}

}
add_action( 'init', 'sarafatto_register_post_meta', 20 );

function sarafatto_sanitize_meta_text( $value ) {
	return sanitize_text_field( is_scalar( $value ) ? (string) $value : '' );
}

function sarafatto_sanitize_story( $value ) {
	return wp_kses_post( is_scalar( $value ) ? (string) $value : '' );
}

/** Keep editorial product images restricted to valid image attachments. */
function sarafatto_sanitize_product_image_id( $value ) {
	$image_id = absint( $value );
	return $image_id && wp_attachment_is_image( $image_id ) ? $image_id : 0;
}

/** Normalize a human-entered amount to a two-decimal numeric string, or false. */
function sarafatto_normalize_price( $value ) {
	if ( ! is_scalar( $value ) ) {
		return false;
	}

	$value = preg_replace( '/[\s\x{00A0}\x{202F}]+/u', '', (string) $value );
	if ( ! is_string( $value ) || '' === $value ) {
		return '';
	}

	if ( ! preg_match( '/^(\d{1,12})(?:[,.](\d{1,2}))?$/', $value, $matches ) ) {
		return false;
	}

	$whole    = ltrim( $matches[1], '0' );
	$whole    = '' === $whole ? '0' : $whole;
	$fraction = isset( $matches[2] ) ? str_pad( $matches[2], 2, '0' ) : '00';

	return $whole . '.' . $fraction;
}

/** Sanitizer for the product price meta field. */
function sarafatto_sanitize_price_meta( $value ) {
	$normalized = sarafatto_normalize_price( $value );
	return false === $normalized ? '' : $normalized;
}

/** Sanitize a short product SKU while preserving common separators. */
function sarafatto_sanitize_sku( $value ) {
	$value = sanitize_text_field( is_scalar( $value ) ? (string) $value : '' );
	return function_exists( 'mb_substr' ) ? mb_substr( $value, 0, 100 ) : substr( $value, 0, 100 );
}

function sarafatto_sanitize_meta_url( $value ) {
	return esc_url_raw( is_scalar( $value ) ? (string) $value : '' );
}

function sarafatto_sanitize_gallery_ids( $value ) {
	if ( ! is_array( $value ) ) {
		return array();
	}

	$attachment_ids = array();
	foreach ( $value as $candidate ) {
		if ( ! is_scalar( $candidate ) ) {
			continue;
		}
		$attachment_id = absint( $candidate );
		if ( $attachment_id && wp_attachment_is_image( $attachment_id ) ) {
			$attachment_ids[] = $attachment_id;
		}
	}

	return array_values( array_unique( $attachment_ids ) );
}

function sarafatto_can_edit_product_meta( $allowed, $meta_key, $post_id ) {
	return current_user_can( 'edit_post', $post_id );
}

