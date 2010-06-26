//
// As mentioned at http://en.wikipedia.org/wiki/XMLHttpRequest
//
if( !window.XMLHttpRequest ) XMLHttpRequest = function()
{
	try{ return new ActiveXObject("Msxml2.XMLHTTP.6.0") }catch(e){}
	try{ return new ActiveXObject("Msxml2.XMLHTTP.3.0") }catch(e){}
	try{ return new ActiveXObject("Msxml2.XMLHTTP") }catch(e){}
	try{ return new ActiveXObject("Microsoft.XMLHTTP") }catch(e){}
	throw new Error("Could not find an XMLHttpRequest alternative.")
};

//
// Makes an AJAX request to a local server function w/ optional arguments
//
// functionName: the name of the server's AJAX function to call
// opt_argv: an Array of arguments for the AJAX function
//
function getRequest(function_name, opt_argv) {

	if (!opt_argv)
		opt_argv = new Array();

	// Find if the last arg is a callback function; save it
	var callback = null;
	var len = opt_argv.length;
	if (len > 0 && typeof opt_argv[len-1] == 'function') {
		callback = opt_argv[len-1];
		opt_argv.length--;
	}
	var async = (callback != null);

	// Encode the arguments in to a URI
	var query = 'action=' + encodeURIComponent(function_name);
	for (var i = 0; i < opt_argv.length; i++) {
		var key = 'arg' + i;
		var val = JSON.stringify(opt_argv[i]);
		query += '&' + key + '=' + encodeURIComponent(val);
	}
	query += '&time=' + new Date().getTime(); // IE cache workaround

	// Create an XMLHttpRequest 'GET' request w/ an optional callback handler
	var req = new XMLHttpRequest();
	req.open('GET', '/rpc?' + query, async);

	if (async) {
		req.onreadystatechange = function() {
			if(req.readyState == 4 && req.status == 200) {
				var response = null;
				try {
					response = JSON.parse(req.responseText);
				} catch (e) {
					response = req.responseText;
				}
				callback(response);
			}
		}
	}

	// Make the actual request
	req.send(null);
}

function postRequest(function_name, opt_argv) {

  if (!opt_argv)
    opt_argv = new Array();

  // Find if the last arg is a callback function; save it
  var callback = null;
  var len = opt_argv.length;
  if (len > 0 && typeof opt_argv[len-1] == 'function') {
    callback = opt_argv[len-1];
    opt_argv.length--;
  }
  var async = (callback != null);

  // Build an Array of parameters, w/ function_name being the first parameter
  var params = new Array(function_name);
  for (var i = 0; i < opt_argv.length; i++) {
    params.push(opt_argv[i]);
  }
  var body = JSON.stringify(params);

  // Create an XMLHttpRequest 'POST' request w/ an optional callback handler
  var req = new XMLHttpRequest();
  req.open('POST', '/rpc', async);

  req.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
  req.setRequestHeader("Content-length", body.length);
  req.setRequestHeader("Connection", "close");

  if (async) {
    req.onreadystatechange = function() {
      if(req.readyState == 4 && req.status == 200) {
        var response = null;
        try {
         response = JSON.parse(req.responseText);
        } catch (e) {
         response = req.responseText;
        }
        callback(response);
      }
    }
  }

  // Make the actual request
  req.send(body);
}


// Adds a stub function that will pass the arguments to the AJAX call
function InstallFunction(obj, functionName, request) {
	obj[functionName] = function() { 
		if (request == "GET")
			getRequest(functionName, arguments); 
		else if (request == "POST")
			postRequest(functionName, arguments);
	}
}

//// Client RPC methods

// Server object that will contain the callable methods
var server = {};

InstallFunction(server, 'sendMsg', "POST");

function doSendMsg(msg) {
	//server.Add($('num1').value, $('num2').value, onAddSuccess);
	server.sendMsg(msg, onAddSuccess);
}

// Callback for after a successful doAdd
function onAddSuccess(response) {
	//$('result').value = response;
	alert("Success=" + response);
}

//// Event handlers

var hasWindowFocus = true;
var defaultTitle = document.title;
var timeoutID;

$(window).blur(function(e) {
	// Change window title
	document.title = "Excel file";
	hasWindowFocus = false;

	// Change favicon
	setFavicon('wordpress');

});

$(window).focus(function(e) {
	document.title = defaultTitle;
	clearInterval(timeoutID);
	timeoutID = null;
	hasWindowFocus = true;

	setFavicon('favicon');
});

$(window).unload(function(e) {
	console.log("unload event");
	// Call AJAX function
	doSendMsg("logout")
});

$(window).bind('beforeunload', 
	function() {
		console.log("beforeunl");
		//return "Do you really want to leave my wonderful chatroom?  But...you mean so much to me.";
		return;
});


function setDocTitle(msg) {
	if(!hasWindowFocus && !timeoutID) {
		// Blink the msg text in the window title
		timeoutID = setInterval(function () {
				document.title = document.title == msg ? ' ' : msg;
			}, 1000);
		setFavicon('M');
	}
}

function setFavicon(file) {
    var link = document.createElement('link');
    link.type = 'image/x-icon';
    link.rel = 'shortcut icon';

	var domain = document.location.href
	domain = domain.replace(/^(https?:\/\/.+\/)\w*$/, "$1")

    link.href = domain + file + '.ico';
    document.getElementsByTagName('head')[0].appendChild(link);
	console.log("setFavIcon to " + link.href)
}

