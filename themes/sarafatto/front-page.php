<?php
/** Front page: render the theme-managed Hero independently from page content. */
get_header();
?>
<main id="main-content" class="site-main site-main--home" tabindex="-1">
	<?php echo sarafatto_render_home_hero(); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
	<?php get_template_part( 'template-parts/home/selection' ); ?>
	<?php get_template_part( 'template-parts/home/discoveries' ); ?>
	<?php get_template_part( 'template-parts/home/shipping-banner' ); ?>
</main>
<?php get_footer();
