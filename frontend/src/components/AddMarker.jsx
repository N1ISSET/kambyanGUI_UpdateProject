import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
// import { LatLng, LatLngExpression } from 'leaflet';
import * as L from "leaflet";
import { Marker, useMapEvents, Popup } from 'react-leaflet';
import jQuery from "jquery";
import axios from "axios";


const reddot = new L.Icon({
    iconUrl: 'static/reddot.svg',
    iconSize: [10, 10]

});

const selectedReddot = new L.Icon({
    iconUrl: 'static/reddot.svg',
    iconSize: [16, 16],
    className: 'selected-marker-icon'
});

function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = jQuery.trim(cookies[i]);
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const MarkerPoint = React.memo(function MarkerPoint({
    pos,
    idx,
    selected,
    markerRef,
    metadata,
    detectionToPreview,
    detectionToSourcePixel,
    removeMarker,
    selectMarker,
    handleDragEnd,
}) {
    const previewPosition = useMemo(() => detectionToPreview(pos), [detectionToPreview, pos]);

    const getTooltipText = useCallback(() => {
        if (metadata) {
            const sourcePixel = detectionToSourcePixel(pos);
            const xCoordinate = (metadata.X_Origin + (sourcePixel.x * metadata.Pixel_SizeX)).toFixed(2);
            const yCoordinate = (metadata.Y_Origin + (sourcePixel.y * metadata.Pixel_SizeY)).toFixed(2);
            return `ID:${idx + 1}, Coordinate: (${xCoordinate}, ${yCoordinate}), Pixel Value: (${sourcePixel.x.toFixed(2)}, ${sourcePixel.y.toFixed(2)})`;
        }

        return `ID:${idx + 1}, Position: (${previewPosition.lat.toFixed(2)}, ${previewPosition.lng.toFixed(2)})`;
    }, [detectionToSourcePixel, idx, metadata, pos, previewPosition]);

    const bindAndOpenTooltip = useCallback(() => {
        const marker = markerRef.current;
        if (!marker) return;
        marker.bindTooltip(getTooltipText());
        marker.openTooltip();
    }, [getTooltipText, markerRef]);

    const closeTooltip = useCallback(() => {
        const marker = markerRef.current;
        if (!marker) return;
        marker.closeTooltip();
        marker.unbindTooltip();
    }, [markerRef]);

    useEffect(() => {
        if (selected) {
            bindAndOpenTooltip();
        } else {
            closeTooltip();
        }
    }, [bindAndOpenTooltip, closeTooltip, selected]);

    const eventHandlers = useMemo(() => ({
        click: (e) => selectMarker(idx, e),
        mouseover: bindAndOpenTooltip,
        mouseout: () => {
            if (!selected) closeTooltip();
        },
        contextmenu: (e) => {
            L.DomEvent.preventDefault(e.originalEvent);
            const marker = markerRef.current;
            if (marker) marker.openPopup();
        },
        dblclick: (e) => {
            selectMarker(idx, e);
        },
        dragend: handleDragEnd(idx),
    }), [bindAndOpenTooltip, closeTooltip, handleDragEnd, idx, markerRef, selectMarker, selected]);

    return (
        <Marker
            icon={selected ? selectedReddot : reddot}
            position={previewPosition}
            draggable={selected}
            ref={(marker) => { markerRef.current = marker; }}
            eventHandlers={eventHandlers}
        >
            <Popup>
                <button onClick={() => removeMarker(pos)}>Remove point</button>
            </Popup>
        </Marker>
    );
});



function AddMarker(props) {
    var csrftoken = getCookie('csrftoken');

    const [coord, setPosition] = useState([]);
    const [selectedIdx, setSelectedIdx] = useState(null);
    const markerRefs = useRef({});
    const { childToParent, imageId, refreshKey } = props;
    const previewScaleX = Number(props.scaleMeta?.scale_x || props.scale || 1);
    const previewScaleY = Number(props.scaleMeta?.scale_y || props.scale || 1);
    const detectionScaleX = Number(props.scaleMeta?.detection_scale_x || 1);
    const detectionScaleY = Number(props.scaleMeta?.detection_scale_y || 1);
    const detectionHeight = Number(props.detectionHeight || props.image_height || 0);

    const detectionToPreview = useCallback((point) => ({
        lat: Number(point.lat) * previewScaleY,
        lng: Number(point.lng) * previewScaleX,
    }), [previewScaleX, previewScaleY]);

    const previewToDetection = useCallback((point) => ({
        lat: Number(point.lat) / previewScaleY,
        lng: Number(point.lng) / previewScaleX,
    }), [previewScaleX, previewScaleY]);

    const detectionToSourcePixel = useCallback((point) => {
        const detectionX = Number(point.lng);
        const detectionY = detectionHeight - Number(point.lat);
        return {
            x: detectionX / detectionScaleX,
            y: detectionY / detectionScaleY,
        };
    }, [detectionHeight, detectionScaleX, detectionScaleY]);

    // Load existing markers from backend on mount
    useEffect(() => {
        if (!imageId) {
            setPosition([]);
            return;
        }

        let cancelled = false;
        const fetchData = async () => {
            let url = `/api/tempdata/?image_id=${encodeURIComponent(imageId)}`;
            try {
                const response = await axios.get(url);
                const data1 = response.data;
                if (!cancelled && Array.isArray(data1)) {
                    setPosition(data1);
                }
            } catch (err) {
                if (!cancelled) {
                    console.error("Error fetching tempdata:", err);
                }
            }
        };
        fetchData();
        return () => {
            cancelled = true;
        };
    }, [imageId, refreshKey]);

    // Click on map → add marker & persist to backend
    useMapEvents({
        click: (e) => {
            if (selectedIdx !== null) {
                setSelectedIdx(null);
                return;
            }

            if (!imageId) return;

            const newPoint = previewToDetection({ lat: e.latlng.lat, lng: e.latlng.lng });
            setPosition((prev) => [...prev, newPoint]);

            // Persist to backend (fire-and-forget)
            axios.post("/api/tempdata/", { ...newPoint, image_id: imageId }, {
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrftoken,
                },
            }).catch((err) => console.error("Error saving new marker:", err));
        }
    });

    useEffect(() => {
        childToParent(coord)
    }, [coord, childToParent]);


    // Remove marker from state & backend
    const removeMarker = useCallback((pos) => {
        setPosition((prevCoord) =>
            prevCoord.filter((c) => JSON.stringify(c) !== JSON.stringify(pos))
        );

        // Delete from backend
        axios.delete("/api/tempdata/", {
            data: { lat: pos.lat, lng: pos.lng, image_id: imageId },
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrftoken,
            },
        }).catch((err) => console.error("Error deleting marker:", err));
    }, [csrftoken, imageId]);

    // Drag end → update state & persist new position to backend
    const handleDragEnd = useCallback((idx) => (e) => {
        const newLatLng = previewToDetection(e.target.getLatLng());
        setPosition((prevCoord) => {
            const oldPos = prevCoord[idx];

            // Update backend with old → new coordinates
            axios.put("/api/tempdata/", {
                old_lat: oldPos.lat,
                old_lng: oldPos.lng,
                lat: newLatLng.lat,
                lng: newLatLng.lng,
                image_id: imageId,
            }, {
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrftoken,
                },
            }).catch((err) => console.error("Error updating marker:", err));

            return prevCoord.map((c, i) =>
                i === idx ? { lat: newLatLng.lat, lng: newLatLng.lng } : c
            );
        });
        setSelectedIdx(null);
    }, [csrftoken, imageId, previewToDetection]);

    const selectMarker = useCallback((idx, event) => {
        L.DomEvent.stopPropagation(event.originalEvent);
        setSelectedIdx(idx);
    }, []);

    const getMarkerRef = useCallback((idx) => {
        if (!markerRefs.current[idx]) {
            markerRefs.current[idx] = React.createRef();
        }
        return markerRefs.current[idx];
    }, []);


    return (
        <div>
            {coord.map((pos, idx) => (
                <MarkerPoint
                    key={idx}
                    pos={pos}
                    idx={idx}
                    selected={selectedIdx === idx}
                    markerRef={getMarkerRef(idx)}
                    metadata={props.metadata}
                    detectionToPreview={detectionToPreview}
                    detectionToSourcePixel={detectionToSourcePixel}
                    removeMarker={removeMarker}
                    selectMarker={selectMarker}
                    handleDragEnd={handleDragEnd}
                />
            ))}
            {/* <Assign Coord={coord}/> */}
        </div>
    );
}


export default React.memo(AddMarker);
