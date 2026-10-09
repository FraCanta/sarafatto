<?php
/** Responsive image frame backed by a WordPress attachment. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$args       = isset( $args ) && is_array( $args ) ? $args : array();
$image_id   = isset( $args['image_id'] ) ? absint( $args['image_id'] ) : 0;
$ratio      = isset( $args['ratio'] ) && in_array( $args['ratio'], array( 'square', 'portrait', 'landscape', 'wide' ), true ) ? $args['ratio'] : '';
$fit        = isset( $args['fit'] ) && 'contain' === $args['fit'] ? 'contain' : 'cover';
$alt        = isset( $args['alt'] ) && is_scalar( $args['alt'] ) ? (string) $args['alt'] : (string) get_post_meta( $image_id, '_wp_attachment_image_alt', true );
$caption    = isset( $args['caption'] ) && is_scalar( $args['caption'] ) ? (string) $args['caption'] : '';
$classes    = array( 'image-frame' );
if ( $ratio ) { $classes[] = 'image-frame--' . $ratio; }
if ( 'contain' === $fit ) { $classes[] = 'image-frame--contain'; }
if ( ! empty( $args['class'] ) && is_array( $args['class'] ) ) { foreach ( $args['class'] as $class ) { if ( is_string( $class ) && sanitize_html_class( $class ) ) { $classes[] = sanitize_html_class( $class ); } } }
if ( ! $image_id || ! wp_attachment_is_image( $image_id ) ) { return; }
?>
<figure class="<?php echo esc_attr( implode( ' ', $classes ) ); ?>">
	<?php echo wp_get_attachment_image( $image_id, $args['size'] ?? 'large', false, array( 'class' => 'image-frame__image', 'alt' => $alt, 'loading' => $args['loading'] ?? 'lazy', 'decoding' => 'async' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
	<?php if ( $caption ) : ?><figcaption class="image-frame__caption"><?php echo esc_html( $caption ); ?></figcaption><?php endif; ?>
</figure>
