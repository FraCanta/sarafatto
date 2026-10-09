<?php
/** Section introduction composed from the shared eyebrow and heading patterns. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$args = isset( $args ) && is_array( $args ) ? $args : array();
?>
<header class="section-intro<?php echo ! empty( $args['class'] ) ? ' ' . esc_attr( sanitize_html_class( $args['class'] ) ) : ''; ?>">
	<?php if ( ! empty( $args['eyebrow'] ) ) { get_template_part( 'template-parts/components/eyebrow', null, array( 'label' => $args['eyebrow'] ) ); } ?>
	<?php get_template_part( 'template-parts/components/editorial-heading', null, array( 'text' => $args['heading'] ?? '', 'tag' => $args['tag'] ?? 'h2', 'size' => $args['size'] ?? 'h2', 'accent' => $args['accent'] ?? '' ) ); ?>
	<?php if ( ! empty( $args['body'] ) ) : ?><div class="section-intro__body"><?php echo wp_kses_post( $args['body'] ); ?></div><?php endif; ?>
</header>
