<?php
/** Small theme helpers. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function sarafatto_skip_link() {
	printf( '<a class="skip-link" href="#main-content">%s</a>', esc_html( sarafatto_theme_label( 'Salta al contenuto', 'Skip to content' ) ) );
}

/** Return a short theme interface label in the current site language. */
function sarafatto_theme_label( $italian, $english ) {
	$language = function_exists( 'sarafatto_get_current_language' ) ? sarafatto_get_current_language() : determine_locale();
	$label    = 0 === strpos( (string) $language, 'en' ) ? $english : $italian;
	return translate( $label, 'sarafatto' );
}
