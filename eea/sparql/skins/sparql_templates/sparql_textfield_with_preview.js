function preview_sparql() {
    var ajax_data = {
            "endpoint" : jQuery("#endpoint_url").prop("value"),
            "timeout" : jQuery("#timeout").prop("value"),
            "arg_spec" : "",
            "sparql_query" : jQuery("#sparql_query").prop("value")
    };
    var preview_arguments = jQuery(".sparql-preview-arguments").prop("value");
    var args_list = preview_arguments.split("&");
    jQuery.each(args_list, function(idx, arg) {
        args = arg.split("=");
        ajax_data[args[0]] = args[1];
    });
    var argspec = jQuery("input[name='arg_spec.name:records']");
    jQuery.each(argspec, function(idx, spec) {
        value = jQuery(spec).prop("value");
        if (value) {
            ajax_data.arg_spec += value + " ";
        }
    });

    var loading_msg = jQuery(
        "<div class='sparql-preview-loading'>" +
        "<div>Executing query...</div></div>");
    jQuery(loading_msg).appendTo("body");
    jQuery.ajax({
        url: portal_url + "/sparql.quick_preview",
        type: "POST",
        data: ajax_data,
        success: function(data) {
            jQuery(".sparql-preview-loading").remove();
            var sparql_preview = jQuery("<div class='sparql_preview'></div>");
            jQuery(data).appendTo(sparql_preview);
            sparql_preview.dialog({
                title: "Preview for " + jQuery("#title").prop("value"),
                modal: true,
                width: 'auto',
                create: function() {
                    $(this).css("maxHeight", 600);
                    $(this).css("maxWidth", 800);
                }
            });
        }
    });
}

function sparql_setstatic() {
    if (jQuery("#sparql_static").prop("checked")) {
        jQuery("#endpoint_url").attr("readonly", true);
        jQuery("#timeout").attr("disabled", true);
        jQuery("#arg_spec").attr("readonly", true);
        jQuery("#sparql_query").attr("readonly", true);

        jQuery("#endpoint_url").addClass("sparql-readonly-field");
        jQuery("#arg_spec").addClass("sparql-readonly-field");
        jQuery("#sparql_query").addClass("sparql-readonly-field");
    }
    else {
        jQuery("#endpoint_url").attr("readonly", false);
        jQuery("#timeout").attr("disabled", false);
        jQuery("#arg_spec").attr("readonly", false);
        jQuery("#sparql_query").attr("readonly", false);
        jQuery(".sparql-readonly-field").removeClass("sparql-readonly-field");
    }
}

function check_relations() {
    if (window.location.href.indexOf("portal_factory") !== -1) {
        return;
    }
    jQuery.ajax({
        url: absolute_url + "/sparql.related_items",
        type: "GET",
        success: function(data) {
            var back_rels = JSON.parse(data);
            if (back_rels.length !== 0) {
                var warningMessage = jQuery(
                    '<dl class="portalMessage warning">' +
                        '<dt>Warning</dt>' +
                        '<div style="clear:both"></div' +
                        '<dd>' +
                            'The result of this query is used by:' +
                            '<ul class="sparql-back-relations"></ul>' +
                            'Modifying the query may cause problems in them.' +
                        '</dd>' +
                    '</dl>');
                jQuery("#sparql-base-edit").prepend(warningMessage);
                jQuery.each(back_rels, function(idx, rel) {
                    var rel_msg = jQuery(
                        '<li><a href="' + rel[1] + '">' + rel[0] + '</a></li>'
                    );
                    rel_msg.appendTo(".sparql-back-relations");
                });
            }
        }
    });

}
jQuery(document).ready(function($) {
    jQuery(".sparql-query-results-preview").click(preview_sparql);
    jQuery("#sparql_static").click(sparql_setstatic);
    sparql_setstatic();
    check_relations();
});
