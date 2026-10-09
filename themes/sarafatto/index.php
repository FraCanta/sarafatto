<?php
/** Fallback template. */
get_header();
?>
<main id="main-content" class="site-main container" tabindex="-1">
	<?php if ( have_posts() ) : while ( have_posts() ) : the_post(); ?>
		<article <?php post_class(); ?>>
			<h1><a href="<?php the_permalink(); ?>"><?php the_title(); ?></a></h1>
			<?php if ( has_post_thumbnail() ) : ?><figure><?php the_post_thumbnail( 'large' ); ?></figure><?php endif; ?>
			<?php the_excerpt(); ?>
		</article>
	<?php endwhile; else : ?><p><?php esc_html_e( 'Non ci sono contenuti da mostrare.', 'sarafatto' ); ?></p><?php endif; ?>
</main>
<?php get_footer();
