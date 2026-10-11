<?php
/** Manual, development-only product detail seeding tools. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function sarafatto_is_dummy_data_environment() {
	if ( ! function_exists( 'wp_get_environment_type' ) ) {
		return false;
	}

	return in_array( wp_get_environment_type(), array( 'local', 'development' ), true );
}

function sarafatto_product_demo_values( $post_id ) {
	$values = array(
		'sarafatto_materials'   => 'Ceramica',
		'sarafatto_dimensions'  => 'Ø 24 cm',
		'sarafatto_colors'      => 'Giallo',
		'sarafatto_variants'    => 'Disponibile in più colori',
		'sarafatto_care'        => 'Lavare a mano con detergente delicato.',
	);
	$flags = function_exists( 'sarafatto_get_product_flags' ) ? sarafatto_get_product_flags( $post_id ) : array();
	if ( ! empty( $flags['personalizable'] ) ) {
		$values['sarafatto_customization_details'] = 'È possibile aggiungere una breve scritta o scegliere alcuni dettagli della personalizzazione. Contatta Sara per verificare le possibilità.';
	}

	return $values;
}

/** Render controls inside the existing product edit form. */
function sarafatto_render_product_demo_tools( $post ) {
	if ( ! sarafatto_is_dummy_data_environment() || ! $post instanceof WP_Post || 'sarafatto_prodotto' !== $post->post_type || ! current_user_can( 'edit_post', $post->ID ) ) {
		return;
	}
	$dummy_values = get_post_meta( $post->ID, 'sarafatto_dummy_details', true );
	$has_dummy    = is_array( $dummy_values ) && $dummy_values;
	wp_nonce_field( 'sarafatto_product_demo_' . $post->ID, 'sarafatto_demo_nonce', false );
	$seed_url   = add_query_arg( array( 'action' => 'sarafatto_seed_product_demo', 'post_id' => $post->ID ), admin_url( 'admin-post.php' ) );
	$remove_url = add_query_arg( array( 'action' => 'sarafatto_remove_product_demo', 'post_id' => $post->ID ), admin_url( 'admin-post.php' ) );
	?>
	<div class="sarafatto-demo-tools">
		<p class="description"><?php esc_html_e( 'Strumenti temporanei di sviluppo. I valori demo compilano solo i campi vuoti e sono tracciati separatamente.', 'sarafatto-core' ); ?></p>
		<button class="button" type="button" data-sarafatto-demo-action="<?php echo esc_url( $seed_url ); ?>" data-product-id="<?php echo esc_attr( $post->ID ); ?>"><?php esc_html_e( 'Compila dati demo', 'sarafatto-core' ); ?></button>
		<?php if ( $has_dummy ) : ?>
			<button class="button" type="button" data-sarafatto-demo-action="<?php echo esc_url( $remove_url ); ?>" data-product-id="<?php echo esc_attr( $post->ID ); ?>"><?php esc_html_e( 'Rimuovi dati demo', 'sarafatto-core' ); ?></button>
		<?php endif; ?>
	</div>
	<?php
}

function sarafatto_handle_product_demo_action( $remove = false ) {
	$request_method = isset( $_SERVER['REQUEST_METHOD'] ) ? strtoupper( sanitize_text_field( wp_unslash( $_SERVER['REQUEST_METHOD'] ) ) ) : '';
	if ( 'POST' !== $request_method ) {
		wp_die( esc_html__( 'Richiesta non valida. Usa il pulsante nella scheda prodotto.', 'sarafatto-core' ), '', array( 'response' => 405 ) );
	}
	if ( ! sarafatto_is_dummy_data_environment() ) {
		wp_die( esc_html__( 'Questa funzione è disponibile solo negli ambienti local e development.', 'sarafatto-core' ), '', array( 'response' => 403 ) );
	}
	$post_id = isset( $_REQUEST['post_id'] ) ? absint( $_REQUEST['post_id'] ) : 0;
	$post    = get_post( $post_id );
	if ( ! $post instanceof WP_Post || 'sarafatto_prodotto' !== $post->post_type || ! current_user_can( 'edit_post', $post_id ) ) {
		wp_die( esc_html__( 'Non hai i permessi per modificare questo prodotto.', 'sarafatto-core' ), '', array( 'response' => 403 ) );
	}
	check_admin_referer( 'sarafatto_product_demo_' . $post_id, 'sarafatto_demo_nonce' );
	$tracked = get_post_meta( $post_id, 'sarafatto_dummy_details', true );
	$tracked = is_array( $tracked ) ? $tracked : array();
	$count   = 0;

	if ( $remove ) {
		foreach ( $tracked as $meta_key => $generated_value ) {
			$current = get_post_meta( $post_id, $meta_key, true );
			if ( (string) $current === (string) $generated_value ) {
				delete_post_meta( $post_id, $meta_key );
				++$count;
			}
		}
		delete_post_meta( $post_id, 'sarafatto_dummy_details' );
		delete_post_meta( $post_id, 'sarafatto_has_dummy_details' );
		$result = 'removed';
	} else {
		foreach ( sarafatto_product_demo_values( $post_id ) as $meta_key => $demo_value ) {
			$current = get_post_meta( $post_id, $meta_key, true );
			if ( is_scalar( $current ) && '' !== trim( (string) $current ) ) {
				continue;
			}
			if ( 'sarafatto_customization_details' === $meta_key ) {
				$legacy_value = get_post_meta( $post_id, 'sarafatto_personalization_details', true );
				if ( is_scalar( $legacy_value ) && '' !== trim( (string) $legacy_value ) ) {
					continue;
				}
			}
			update_post_meta( $post_id, $meta_key, $demo_value );
			$tracked[ $meta_key ] = $demo_value;
			++$count;
		}
		if ( ! metadata_exists( 'post', $post_id, 'sarafatto_is_handmade' ) ) {
			update_post_meta( $post_id, 'sarafatto_is_handmade', '1' );
			$tracked['sarafatto_is_handmade'] = '1';
			++$count;
		}
		if ( $tracked ) {
			update_post_meta( $post_id, 'sarafatto_dummy_details', $tracked );
			update_post_meta( $post_id, 'sarafatto_has_dummy_details', '1' );
		}
		$result = 'seeded';
	}

	$redirect = add_query_arg( array( 'post' => $post_id, 'action' => 'edit', 'sarafatto_demo' => $result, 'sarafatto_demo_count' => $count ), admin_url( 'post.php' ) );
	wp_safe_redirect( $redirect );
	exit;
}
add_action( 'admin_post_sarafatto_seed_product_demo', 'sarafatto_handle_product_demo_action' );
add_action( 'admin_post_sarafatto_remove_product_demo', function () { sarafatto_handle_product_demo_action( true ); } );

function sarafatto_product_demo_admin_notice() {
	if ( ! sarafatto_is_dummy_data_environment() || ! isset( $_GET['sarafatto_demo'] ) || ! function_exists( 'get_current_screen' ) ) {
		return;
	}
	$screen = get_current_screen();
	if ( ! $screen || 'sarafatto_prodotto' !== $screen->post_type ) {
		return;
	}
	$result = sanitize_key( wp_unslash( $_GET['sarafatto_demo'] ) );
	$count  = isset( $_GET['sarafatto_demo_count'] ) ? absint( $_GET['sarafatto_demo_count'] ) : 0;
	if ( ! in_array( $result, array( 'seeded', 'removed' ), true ) ) {
		return;
	}
	$message = 'seeded' === $result
		? sprintf( _n( '%d valore demo aggiunto. Sostituiscilo con i dati reali prima della pubblicazione.', '%d valori demo aggiunti. Sostituiscili con i dati reali prima della pubblicazione.', $count, 'sarafatto-core' ), $count )
		: sprintf( _n( '%d valore demo rimosso; eventuali valori modificati manualmente sono stati conservati.', '%d valori demo rimossi; eventuali valori modificati manualmente sono stati conservati.', $count, 'sarafatto-core' ), $count );
	?>
	<div class="notice notice-info is-dismissible"><p><?php echo esc_html( $message ); ?></p></div>
	<?php
}
add_action( 'admin_notices', 'sarafatto_product_demo_admin_notice' );
