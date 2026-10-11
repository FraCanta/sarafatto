<?php
/** Keep Polylang's static front page at each language root URL. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Apply Polylang's built-in language-root front page behavior without saving its option. */
function sarafatto_polylang_language_root_front_page_option( $options ) {
	if ( ! is_array( $options ) || 'page' !== get_option( 'show_on_front' ) ) {
		return $options;
	}

	$options['redirect_lang'] = 1;
	return $options;
}
add_filter( 'option_polylang', 'sarafatto_polylang_language_root_front_page_option' );
