<?php
/** Configurable semantic heading; its text is always escaped as text. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$args   = isset( $args ) && is_array( $args ) ? $args : array();
$text   = isset( $args['text'] ) && is_scalar( $args['text'] ) ? (string) $args['text'] : '';
$requested_tag = isset( $args['tag'] ) && is_string( $args['tag'] ) ? strtolower( $args['tag'] ) : '';
$tag           = in_array( $requested_tag, array( 'h1', 'h2', 'h3', 'h4', 'h5', 'h6' ), true ) ? $requested_tag : 'h2';
$size   = isset( $args['size'] ) && in_array( $args['size'], array( 'display-xl', 'display-lg', 'h1', 'h2', 'h3' ), true ) ? $args['size'] : 'h2';
$accent = isset( $args['accent'] ) && in_array( $args['accent'], array( 'brand', 'pink', 'yellow' ), true ) ? $args['accent'] : '';
$classes = array( 'editorial-heading', 'editorial-heading--' . $size );
if ( ! empty( $args['class'] ) && is_array( $args['class'] ) ) {
	foreach ( $args['class'] as $class ) { if ( is_string( $class ) && sanitize_html_class( $class ) ) { $classes[] = sanitize_html_class( $class ); } }
}
if ( ! $text ) { return; }
?>
<<?php echo esc_html( $tag ); ?> class="<?php echo esc_attr( implode( ' ', $classes ) ); ?>"><?php if ( $accent ) : ?><span class="editorial-heading__accent--<?php echo esc_attr( $accent ); ?>"><?php echo esc_html( $text ); ?></span><?php else : echo esc_html( $text ); endif; ?></<?php echo esc_html( $tag ); ?>>
