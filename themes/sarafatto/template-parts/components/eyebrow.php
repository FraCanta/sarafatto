<?php
/** Small editorial label. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$args  = isset( $args ) && is_array( $args ) ? $args : array();
$label = isset( $args['label'] ) && is_scalar( $args['label'] ) ? (string) $args['label'] : '';
if ( ! $label ) { return; }
?><p class="eyebrow<?php echo ! empty( $args['class'] ) ? ' ' . esc_attr( sanitize_html_class( $args['class'] ) ) : ''; ?>"><?php echo esc_html( $label ); ?></p>
