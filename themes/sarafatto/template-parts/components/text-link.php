<?php
/** Text link with optional editorial arrow. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$args     = isset( $args ) && is_array( $args ) ? $args : array();
$label    = isset( $args['label'] ) && is_scalar( $args['label'] ) ? (string) $args['label'] : '';
$url      = isset( $args['url'] ) ? esc_url( $args['url'] ) : '';
$external = ! empty( $args['external'] );
if ( ! $label || ! $url ) { return; }
?>
<a class="text-link<?php echo ! empty( $args['class'] ) ? ' ' . esc_attr( sanitize_html_class( $args['class'] ) ) : ''; ?>" href="<?php echo esc_url( $url ); ?>"<?php echo $external ? ' target="_blank" rel="noopener noreferrer"' : ''; ?>>
	<span><?php echo esc_html( $label ); ?></span><?php if ( ! empty( $args['arrow'] ) ) : ?><span class="text-link__arrow" aria-hidden="true">→</span><?php endif; ?><?php if ( $external ) : ?><span class="screen-reader-text"> (<?php echo esc_html( sarafatto_theme_label( 'si apre in una nuova scheda', 'opens in a new tab' ) ); ?>)</span><?php endif; ?>
</a>
