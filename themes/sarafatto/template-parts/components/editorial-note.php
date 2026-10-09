<?php
/** Editorial note with a limited set of accent variants. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$args    = isset( $args ) && is_array( $args ) ? $args : array();
$message = isset( $args['text'] ) && is_scalar( $args['text'] ) ? (string) $args['text'] : '';
$label   = isset( $args['label'] ) && is_scalar( $args['label'] ) ? (string) $args['label'] : '';
$tone    = isset( $args['tone'] ) && in_array( $args['tone'], array( 'brand', 'pink', 'yellow' ), true ) ? $args['tone'] : 'yellow';
if ( ! $message ) { return; }
?>
<aside class="editorial-note editorial-note--<?php echo esc_attr( $tone ); ?>" role="note">
	<?php if ( $label ) : ?><p class="editorial-note__label"><?php echo esc_html( $label ); ?></p><?php endif; ?>
	<p class="editorial-note__body"><?php echo esc_html( $message ); ?></p>
</aside>
