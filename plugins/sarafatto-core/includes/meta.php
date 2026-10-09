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
		'sarafatto_story'           => array( 'string', 'sarafatto_sanitize_story' ),
		'sarafatto_gallery'         => array( 'array', 'sarafatto_sanitize_gallery_ids' ),
	);

	foreach ( $product_meta as $meta_key => $field ) {
		$meta_args = array(
			'type'              => $field[0],
			'single'            => true,
			'revisions_enabled' => true,
			'sanitize_callback' => $field[1],
			'auth_callback'     => 'sarafatto_can_edit_product_meta',
		);
		if ( in_array( $meta_key, array( 'sarafatto_is_new', 'sarafatto_is_featured' ), true ) ) {
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

