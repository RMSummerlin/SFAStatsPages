<?php
/**
 * Sharp Football Analysis — server-side preload tables.
 *
 * Renders the crawlable stat tables into the page HTML so search engines and
 * no-JavaScript visitors see real data. The interactive tools replace them on
 * load; if a tool's data fetch fails, the server-rendered table stays visible,
 * which makes this the fallback as well as the SEO path.
 *
 * Shortcodes:
 *   [sharp_football_personnel]   personnel grouping frequency
 *   [sharp_football_pace]        offensive pace
 *
 * All of them read one cached manifest, so two shortcodes on one page cost a
 * single HTTP request — and so do two shortcodes on different pages, because
 * the cache is shared.
 *
 * Install: paste into Code Snippets (run everywhere), or into the child theme's
 * functions.php. No configuration needed.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

// Bail out rather than fatal if this ends up pasted in twice.
if ( function_exists( 'sfa_preload_render' ) ) {
	return;
}

define( 'SFA_PRELOAD_URL', 'https://rmsummerlin.github.io/SFAStatsPages/data/preloads.json' );
// The tables are refreshed once a week, because the sheets are only topped up
// once a week and almost always on a Tuesday. Anything more often spends a
// blocking HTTP request for a file that has not changed.
define( 'SFA_PRELOAD_TIMEZONE', 'America/New_York' );
define( 'SFA_PRELOAD_REFRESH_DAY', 'tuesday' );
define( 'SFA_PRELOAD_REFRESH_TIME', '23:00' );
define( 'SFA_PRELOAD_RETRY', 120 );      // after a failed fetch, wait this long before retrying
define( 'SFA_PRELOAD_LOCK_TTL', 30 );    // how long one refresh may hold the lock
define( 'SFA_PRELOAD_OPTION', 'sfa_preloads_last_good' );
define( 'SFA_PRELOAD_LOCK', 'sfa_preloads_lock' );
define( 'SFA_PRELOAD_TRANSIENT', 'sfa_preloads_html' );

/**
 * Seconds until the next scheduled refresh.
 *
 * Anchored to a wall-clock moment rather than a rolling duration, so the cache
 * always turns over just after the week's data has landed instead of drifting
 * by however long ago the last page view happened to be.
 */
function sfa_preload_ttl() {
	try {
		$tz   = new DateTimeZone( SFA_PRELOAD_TIMEZONE );
		$now  = new DateTime( 'now', $tz );
		// 'tuesday 23:00' resolves to today when today is a Tuesday, so the
		// comparison below is what rolls it forward once the moment has passed.
		$next = new DateTime(
			SFA_PRELOAD_REFRESH_DAY . ' ' . SFA_PRELOAD_REFRESH_TIME, $tz );
		if ( $now >= $next ) {
			$next->modify( '+7 days' );
		}
		return max( $next->getTimestamp() - $now->getTimestamp(), MINUTE_IN_SECONDS );
	} catch ( Exception $e ) {
		return WEEK_IN_SECONDS;  // never let a date problem break the page
	}
}

/**
 * Tags permitted in the fetched HTML.
 *
 * The manifest comes from our own repo over HTTPS, but it is still remote HTML
 * being echoed into every article. Restricting it to table markup means that
 * even if the source were tampered with, nothing executable can reach the page.
 */
function sfa_preload_allowed_tags() {
	$cell = array(
		'scope'   => true,
		'colspan' => true,
		'rowspan' => true,
		'class'   => true,
	);
	return array(
		'table'   => array( 'class' => true ),
		'caption' => array( 'class' => true ),
		'thead'   => array(),
		'tbody'   => array(),
		'tfoot'   => array(),
		'tr'      => array( 'class' => true ),
		'th'      => $cell,
		'td'      => $cell,
		'span'    => array( 'class' => true ),
		'b'       => array(),
		'strong'  => array(),
		'em'      => array(),
		'i'       => array(),
		'abbr'    => array( 'title' => true ),
	);
}

/**
 * Fetch the manifest. Returns an array of tool => html, or null on any failure.
 */
function sfa_preload_fetch() {
	$response = wp_remote_get(
		SFA_PRELOAD_URL,
		array(
			'timeout'    => 4,
			'user-agent' => 'SFAStatsPages preload/1.0',
			'headers'    => array( 'Accept' => 'application/json' ),
		)
	);

	$failed = '';
	if ( is_wp_error( $response ) ) {
		$failed = 'wp_error: ' . $response->get_error_message();
	} elseif ( 200 !== (int) wp_remote_retrieve_response_code( $response ) ) {
		$failed = 'http ' . wp_remote_retrieve_response_code( $response );
	}
	if ( $failed ) {
		error_log( 'sfa_preloads: fetch failed (' . $failed . ') for ' . SFA_PRELOAD_URL );
		return null;
	}

	$decoded = json_decode( wp_remote_retrieve_body( $response ), true );
	if ( ! is_array( $decoded ) || empty( $decoded ) ) {
		error_log( 'sfa_preloads: response was not a JSON object for ' . SFA_PRELOAD_URL );
		return null;
	}

	// Sanitised here, once per fetch, rather than on every page render. wp_kses
	// is regex-heavy and the result is identical every time, so there is no
	// reason to pay for it per request.
	$clean = array();
	foreach ( $decoded as $key => $html ) {
		if ( is_string( $key ) && is_string( $html ) && '' !== trim( $html ) ) {
			$clean[ sanitize_key( $key ) ] = wp_kses( $html, sfa_preload_allowed_tags() );
		}
	}
	if ( empty( $clean ) ) {
		error_log( 'sfa_preloads: nothing survived sanitising for ' . SFA_PRELOAD_URL );
		return null;
	}
	return $clean;
}

/**
 * Cached manifest.
 *
 * The payload lives in an option rather than a transient so it survives cache
 * expiry: if GitHub is briefly unreachable we serve the last good copy instead
 * of rendering an empty table on a live article. The timestamp decides when to
 * try again, and a short lock stops concurrent requests all refreshing at once.
 */
function sfa_preload_manifest() {
	static $memo = null;
	if ( null !== $memo ) {
		return $memo;  // one lookup per request, however many shortcodes run
	}

	$forced = isset( $_GET['sfa_refresh'] ) && current_user_can( 'edit_posts' );

	if ( ! $forced ) {
		$cached = get_transient( SFA_PRELOAD_TRANSIENT );
		if ( false !== $cached ) {
			$memo = is_array( $cached ) ? $cached : array();
			return $memo;
		}
	}

	// Only one request should refresh when the cache expires; the rest fall
	// through to the last good copy for a moment.
	if ( ! $forced && false !== get_transient( SFA_PRELOAD_LOCK ) ) {
		$memo = (array) get_option( SFA_PRELOAD_OPTION, array() );
		return $memo;
	}
	set_transient( SFA_PRELOAD_LOCK, 1, SFA_PRELOAD_LOCK_TTL );

	$fresh = sfa_preload_fetch();
	delete_transient( SFA_PRELOAD_LOCK );

	if ( null === $fresh ) {
		// Serve the last good snapshot and retry shortly, rather than rendering
		// an empty table on a live article.
		$fallback = (array) get_option( SFA_PRELOAD_OPTION, array() );
		set_transient( SFA_PRELOAD_TRANSIENT, $fallback, SFA_PRELOAD_RETRY );
		$memo = $fallback;
		return $memo;
	}

	update_option( SFA_PRELOAD_OPTION, $fresh, false );  // no autoload
	set_transient( SFA_PRELOAD_TRANSIENT, $fresh, sfa_preload_ttl() );
	$memo = $fresh;
	return $memo;
}

/**
 * Render one tool's table.
 */
function sfa_preload_render( $tool ) {
	$manifest = sfa_preload_manifest();
	$tool     = sanitize_key( $tool );

	if ( empty( $manifest[ $tool ] ) ) {
		// Never break the page. Leave a trace an editor can find in view-source.
		return '<!-- sfa preload: no table available for ' . esc_html( $tool ) . ' -->';
	}

	// Already sanitised at fetch time.
	$html = $manifest[ $tool ];

	// data-sfa-preload lets the interactive tool hide this once it has rendered,
	// wherever on the page it sits. If the tool's fetch fails it stays visible.
	return '<div class="sfa-preload" data-sfa-preload="' . esc_attr( $tool ) . '">'
		. $html . '</div>';
}

/*
 * One shortcode per tool, deliberately, so they read clearly in the CMS. They
 * all share the cache above, so the count of shortcodes does not affect the
 * number of requests. To add a tool: add a line here matching its key in
 * data/preloads.json.
 */
add_shortcode(
	'sharp_football_personnel',
	function () {
		return sfa_preload_render( 'personnel_grouping' );
	}
);

add_shortcode(
	'sharp_football_pace',
	function () {
		return sfa_preload_render( 'pace' );
	}
);

/*
 * No deactivation hook: that is plugin-only, and inside Code Snippets __FILE__
 * is not this snippet, so it would silently do the wrong thing. To clear the
 * stored copy, load any page carrying a shortcode with ?sfa_refresh=1 while
 * logged in as an editor, or delete the sfa_preloads_cache option.
 */
