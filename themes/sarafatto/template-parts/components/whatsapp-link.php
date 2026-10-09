<?php
/** WhatsApp link using the configured global number and message helper. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$args = isset( $args ) && is_array( $args ) ? $args : array();
if ( ! function_exists( 'sarafatto_get_whatsapp_url' ) ) { return; }
$product_id = isset( $args['product_id'] ) ? absint( $args['product_id'] ) : 0;
$message    = isset( $args['message'] ) && is_scalar( $args['message'] ) ? (string) $args['message'] : '';
if ( $product_id && function_exists( 'sarafatto_get_product_whatsapp_url' ) ) {
	$url = sarafatto_get_product_whatsapp_url( $product_id );
} else {
	if ( $product_id && ! $message ) {
		$template = 'Ciao! Vorrei avere qualche informazione su %s.';
		if ( function_exists( 'sarafatto_translate_dynamic_string' ) ) { $template = sarafatto_translate_dynamic_string( $template ); }
		$message = sprintf( $template, get_the_title( $product_id ) );
	}
	$url = sarafatto_get_whatsapp_url( $message );
}
$label = isset( $args['label'] ) && is_scalar( $args['label'] ) ? (string) $args['label'] : '';
$mobile_label = isset( $args['mobile_label'] ) && is_scalar( $args['mobile_label'] ) ? (string) $args['mobile_label'] : '';
$class = isset( $args['class'] ) && is_scalar( $args['class'] )
	? implode( ' ', array_filter( array_map( 'sanitize_html_class', preg_split( '/\s+/', (string) $args['class'] ) ) ) )
	: '';
$link_classes = $class ? $class : 'text-link';
if ( ! $label && $product_id ) { $label = sarafatto_theme_label( 'Chiedi informazioni su WhatsApp', 'Ask about this product on WhatsApp' ); }
if ( ! $url || ! $label ) { return; }
?>
<a class="<?php echo esc_attr( $link_classes ); ?>" href="<?php echo esc_url( $url ); ?>" target="_blank" rel="noopener noreferrer">
	<?php if ( isset( $args['icon'] ) && 'whatsapp' === $args['icon'] ) : ?>
		<svg class="button__icon site-header__whatsapp-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M20.52 3.48A11.86 11.86 0 0 0 12.08 0C5.5 0 .14 5.35.14 11.93c0 2.1.55 4.16 1.6 5.97L0 24l6.26-1.64a11.95 11.95 0 0 0 5.81 1.48h.01c6.58 0 11.93-5.35 11.93-11.93 0-3.19-1.24-6.19-3.49-8.43ZM12.08 21.8a9.9 9.9 0 0 1-5.04-1.38l-.36-.21-3.72.97.99-3.62-.23-.37a9.88 9.88 0 0 1-1.52-5.26c0-5.45 4.44-9.89 9.9-9.89a9.82 9.82 0 0 1 7 2.9 9.82 9.82 0 0 1 2.9 7c0 5.45-4.45 9.88-9.92 9.88Zm5.43-7.4c-.3-.15-1.77-.87-2.05-.97-.28-.1-.47-.15-.67.15-.2.3-.77.97-.94 1.17-.17.2-.35.22-.65.07-.3-.15-1.26-.46-2.4-1.47-.89-.79-1.49-1.77-1.66-2.07-.18-.3-.02-.46.13-.61.13-.13.3-.35.45-.52.15-.18.2-.3.3-.5.1-.2.05-.38-.03-.53-.07-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.8.37-.28.3-1.04 1.02-1.04 2.49 0 1.47 1.07 2.89 1.22 3.09.15.2 2.1 3.2 5.08 4.49.71.31 1.27.5 1.7.63.71.23 1.36.2 1.87.12.57-.08 1.77-.72 2.02-1.42.25-.7.25-1.3.17-1.42-.07-.13-.27-.2-.57-.35Z"/></svg>
	<?php endif; ?>
	<?php if ( isset( $args['icon'] ) && 'whatsapp' === $args['icon'] ) : ?>
		<span class="site-header__whatsapp-label--desktop" aria-hidden="true"><?php echo esc_html( $label ); ?></span>
		<span class="screen-reader-text"><?php echo esc_html( $label ); ?></span>
	<?php elseif ( $mobile_label ) : ?>
		<span class="site-header__whatsapp-label--desktop"><?php echo esc_html( $label ); ?></span>
		<span class="site-header__whatsapp-label--mobile" aria-hidden="true"><?php echo esc_html( $mobile_label ); ?></span>
	<?php else : ?>
		<span><?php echo esc_html( $label ); ?></span>
	<?php endif; ?>
	<span class="screen-reader-text"> (<?php esc_html_e( 'si apre in una nuova scheda', 'sarafatto' ); ?>)</span>
</a>
