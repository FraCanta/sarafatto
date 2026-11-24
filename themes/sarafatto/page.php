<?php
/** Default page template. */

$gift_ideas_page_id = function_exists( 'sarafatto_get_linked_page_id' ) ? sarafatto_get_linked_page_id( 'idee_regalo' ) : 0;
if ( $gift_ideas_page_id && is_page( $gift_ideas_page_id ) ) {
	get_header();
	get_template_part( 'template-parts/pages/gift-ideas' );
	get_footer();
	return;
}

$personalized_page_id = function_exists( 'sarafatto_get_linked_page_id' ) ? sarafatto_get_linked_page_id( 'personalizzati' ) : 0;
if ( ( $personalized_page_id && is_page( $personalized_page_id ) ) || is_page( array( 'personalizzati', 'personalised' ) ) ) {
	get_header();
	get_template_part( 'template-parts/pages/personalizzati' );
	get_footer();
	return;
}

$contact_page_id = function_exists( 'sarafatto_get_linked_page_id' ) ? sarafatto_get_linked_page_id( 'contatti' ) : 0;
if ( ( $contact_page_id && is_page( $contact_page_id ) ) || is_page( array( 'contatti', 'contact' ) ) ) {
	get_header();
	get_template_part( 'template-parts/pages/contact' );
	get_footer();
	return;
}

get_header();
?>
<main id="main-content" class="site-main site-main--standard-page" tabindex="-1">
	<?php while ( have_posts() ) : the_post(); ?>
		<?php
		get_template_part(
			'template-parts/components/page-hero',
			null,
			array(
				'title' => get_the_title(),
				'breadcrumbs' => array(
					array( 'label' => sarafatto_theme_label( 'Home', 'Home' ), 'url' => function_exists( 'sarafatto_get_language_home_url' ) ? sarafatto_get_language_home_url() : home_url( '/' ) ),
					array( 'label' => get_the_title() ),
				),
			)
		);
		?>
		<div class="container">
		<article <?php post_class(); ?>>
			<?php if ( has_post_thumbnail() ) : ?><figure><?php the_post_thumbnail( 'large' ); ?></figure><?php endif; ?>
			<?php the_content(); ?>
		</article>
		</div>
	<?php endwhile; ?>
</main>
<?php get_footer();
