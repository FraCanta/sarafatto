<?php
/** Editorial button. Pass label, href (optional), variant, icon, type and state. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$args       = isset( $args ) && is_array( $args ) ? $args : array();
$label      = isset( $args['label'] ) && is_scalar( $args['label'] ) ? (string) $args['label'] : '';
$href       = isset( $args['href'] ) && is_scalar( $args['href'] ) ? (string) $args['href'] : '';
$variant    = isset( $args['variant'] ) && in_array( $args['variant'], array( 'primary', 'accent', 'secondary', 'text' ), true ) ? $args['variant'] : 'primary';
$size       = isset( $args['size'] ) && in_array( $args['size'], array( 'sm', 'md', 'lg' ), true ) ? $args['size'] : 'md';
$icon       = isset( $args['icon'] ) && is_scalar( $args['icon'] ) ? (string) $args['icon'] : '';
$icon_position = isset( $args['icon_position'] ) && in_array( $args['icon_position'], array( 'before', 'after' ), true ) ? $args['icon_position'] : 'before';
$disabled   = ! empty( $args['disabled'] );
$external   = ! empty( $args['external'] );
$mobile_icon_only = ! empty( $args['mobile_icon_only'] );
$type       = isset( $args['type'] ) && in_array( $args['type'], array( 'button', 'submit', 'reset' ), true ) ? $args['type'] : 'button';
$extra_classes = isset( $args['class'] ) && is_scalar( $args['class'] )
	? array_filter( array_map( 'sanitize_html_class', preg_split( '/\s+/', (string) $args['class'] ) ) )
	: array();
$class_name = implode( ' ', array_merge( array( 'button', 'button--' . $variant, 'button--' . $size ), $mobile_icon_only ? array( 'button--mobile-icon-only' ) : array(), $extra_classes ) );
if ( 'whatsapp' === $icon ) {
	$icon_markup = '<svg class="button__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M20.52 3.48A11.86 11.86 0 0 0 12.08 0C5.5 0 .14 5.35.14 11.93c0 2.1.55 4.16 1.6 5.97L0 24l6.26-1.64a11.95 11.95 0 0 0 5.81 1.48h.01c6.58 0 11.93-5.35 11.93-11.93 0-3.19-1.24-6.19-3.49-8.43ZM12.08 21.8a9.9 9.9 0 0 1-5.04-1.38l-.36-.21-3.72.97.99-3.62-.23-.37a9.88 9.88 0 0 1-1.52-5.26c0-5.45 4.44-9.89 9.9-9.89a9.82 9.82 0 0 1 7 2.9 9.82 9.82 0 0 1 2.9 7c0 5.45-4.45 9.88-9.92 9.88Zm5.43-7.4c-.3-.15-1.77-.87-2.05-.97-.28-.1-.47-.15-.67.15-.2.3-.77.97-.94 1.17-.17.2-.35.22-.65.07-.3-.15-1.26-.46-2.4-1.47-.89-.79-1.49-1.77-1.66-2.07-.18-.3-.02-.46.13-.61.13-.13.3-.35.45-.52.15-.18.2-.3.3-.5.1-.2.05-.38-.03-.53-.07-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.8.37-.28.3-1.04 1.02-1.04 2.49 0 1.47 1.07 2.89 1.22 3.09.15.2 2.1 3.2 5.08 4.49.71.31 1.27.5 1.7.63.71.23 1.36.2 1.87.12.57-.08 1.77-.72 2.02-1.42.25-.7.25-1.3.17-1.42-.07-.13-.27-.2-.57-.35Z"/></svg>';
	} elseif ( 'arrow-up-right' === $icon ) {
		$icon_markup = '<span class="button__icon icon-[mdi--arrow-top-right]" aria-hidden="true"></span>';
	} elseif ( 'arrow-right' === $icon ) {
		$icon_markup = '<span class="button__icon icon-[mdi--arrow-right]" aria-hidden="true"></span>';
} elseif ( $icon ) {
	$icon_markup = '<span class="button__icon" aria-hidden="true">' . esc_html( $icon ) . '</span>';
} else {
	$icon_markup = '';
}
if ( ! $label ) { return; }
if ( $href && ! $disabled ) :
?>
<a class="<?php echo esc_attr( $class_name ); ?>" href="<?php echo esc_url( $href ); ?>"<?php echo $external ? ' target="_blank" rel="noopener noreferrer"' : ''; ?>>
	<?php if ( 'before' === $icon_position ) { echo $icon_markup; } ?><span class="button__label"><?php echo esc_html( $label ); ?></span><?php if ( 'after' === $icon_position ) { echo $icon_markup; } ?><?php if ( $external ) : ?><span class="screen-reader-text"> (<?php echo esc_html( sarafatto_theme_label( 'si apre in una nuova scheda', 'opens in a new tab' ) ); ?>)</span><?php endif; ?>
</a>
<?php else : ?>
<button class="<?php echo esc_attr( $class_name ); ?>" type="<?php echo esc_attr( $type ); ?>"<?php disabled( $disabled ); ?>>
	<?php if ( 'before' === $icon_position ) { echo $icon_markup; } ?><span class="button__label"><?php echo esc_html( $label ); ?></span><?php if ( 'after' === $icon_position ) { echo $icon_markup; } ?>
</button>
<?php endif; ?>
