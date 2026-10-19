<?php
/** Default page template. */

$gift_ideas_page_id = function_exists( 'sarafatto_get_linked_page_id' ) ? sarafatto_get_linked_page_id( 'idee_regalo' ) : 0;
if ( $gift_ideas_page_id && is_page( $gift_ideas_page_id ) ) {
	get_header();
	get_template_part( 'template-parts/pages/gift-ideas' );
	get_footer();
	return;
}

get_header();
?>
<main id="main-content" class="site-main container" tabindex="-1">
	<?php while ( have_posts() ) : the_post(); ?>
		<article <?php post_class(); ?>>
			<?php $page_title = get_the_title(); ?>
			<h1>
				<?php if ( in_array( sanitize_title( $page_title ), array( 'novita', 'new-arrivals' ), true ) ) : ?>
					<span class="editorial-underline editorial-underline--02"><?php echo esc_html( $page_title ); ?></span>
				<?php else : ?>
					<?php echo esc_html( $page_title ); ?>
				<?php endif; ?>
			</h1>
			<?php if ( has_post_thumbnail() ) : ?><figure><?php the_post_thumbnail( 'large' ); ?></figure><?php endif; ?>
			<?php the_content(); ?>
		</article>
	<?php endwhile; ?>
</main>
<?php get_footer();
