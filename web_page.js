
// references ip_address from dynamically generated ip_address.js

const port = "8000";
address = ip_address + ':' + port;
const url='http://' + address;

document.getElementById('title').firstChild.textContent="stream2cca running at ".concat(url);

// regularly call get_status() every 1000 ms
var status_interval = setInterval(get_status, 1000);

function vol_toggle_mute(){
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("volume_toggle_mute");
}

function vol_down(){
    //alert("Vol - from JS");
    //document.getElementById('status0').firstChild.textContent="Vol - from JS";
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("volume_down");
}

function vol_up(){
    //alert("Vol + from JS");
    //document.getElementById('status0').firstChild.textContent="Vol + from JS";
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("volume_up");
}

function prev_track(){
    //document.getElementById('status0').firstChild.textContent="Pause/Resume Toggle";
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("prev_track");
}

function next_track(){
    //document.getElementById('status0').firstChild.textContent="Pause/Resume Toggle";
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("next_track");
}

function toggle_pause(){
    //document.getElementById('status0').firstChild.textContent="Pause/Resume Toggle";
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("toggle_pause");
}

function get_status(){
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("get_status");

    Http.onreadystatechange = (e) => {
        status_text = Http.responseText
        status_array = status_text.split(/\r?\n/);
        //console.log(status_text)
        //console.log(status_array)
        document.getElementById('status0').firstChild.textContent = status_array[0];
        document.getElementById('status1').firstChild.textContent = status_array[1];
        document.getElementById('status2').firstChild.textContent = status_array[2];

        // Initialize a static variable for previous track
        if ( typeof this.prev_track_status == 'undefined' ) {
            this.prev_track_status = "";
        }

        // refresh img if track has changed
        track_status = status_array[1];
        if(this.prev_track_status.localeCompare(track_status) != 0) {
            // filter out spurious assignments of 'undefined' 
            // (not sure why we get these...)
            if("undefined".localeCompare(track_status) != 0) {
                console.log("Track status changed to: " + track_status)
                refresh_img();
                this.prev_track_status = track_status;
            }
        }
    }
}

function refresh_img(){
    // append #Date.now() as technique to force reload (avoid cache)
    // - also requires some Cache-Control headers from the server
    // see: https://stackoverflow.com/questions/1077041/refresh-image-with-a-new-one-at-the-same-url
    document.getElementById('cover_art').src="cover.jpg#" + Date.now();
}

