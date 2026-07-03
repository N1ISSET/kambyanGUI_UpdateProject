import React, { useState, useRef, useEffect } from 'react';
import Modal from "react-bootstrap/Modal";
import "bootstrap/dist/css/bootstrap.min.css";
import Button from 'react-bootstrap/Button';
import jQuery from "jquery";
import { Alert } from 'react-bootstrap';
import useDraggable from "../useDraggable"
import "./modal.css";
import Resizer from "react-image-file-resizer";


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

function getProxiedMediaUrl(url) {
    if (!url) return "";

    try {
        const parsedUrl = new URL(url, window.location.origin);
        const isLocalBackend =
            parsedUrl.hostname === "localhost" ||
            parsedUrl.hostname === "127.0.0.1";

        // A browser on another device must not request its own localhost.
        if (isLocalBackend) {
            return `${parsedUrl.pathname}${parsedUrl.search}`;
        }

        return parsedUrl.href;
    } catch (error) {
        return url;
    }
}


function ImageScaling(props) {
    const { imgdata, autoscale, scaleshow, ...modalProps } = props;

    var csrftoken = getCookie('csrftoken');

    const [image, setImage] = useState();
    const [showDangerAlert, setshowDangerAlert] = useState(false);
    const [showSuccessAlert, setshowSuccessAlert] = useState(false);
    const [scaleimg, setScaleImg] = useState();
    const [scale, setScale] = useState(1);
    const [imageWidth, setImageWidth] = useState();
    const [imageHeight, setImageHeight] = useState();
    const [done, setDone] = useState(true);
    const [errorMessage, setErrorMessage] = useState("This is a error Message");

   

    useEffect(() => {
        if (!scaleshow || !imgdata?.image_file) {
            return;
        }

        let cancelled = false;
        const imageUrl = getProxiedMediaUrl(imgdata.image_file);

        setImage(undefined);
        setScaleImg(undefined);
        setImageWidth(undefined);
        setImageHeight(undefined);
        setDone(false);
        setshowDangerAlert(false);
        setshowSuccessAlert(false);

        fetch(imageUrl)
            .then(res => {
                if (!res.ok) {
                    throw new Error("Unable to load the selected image.");
                }
                return res.blob();
            })
            .then(blob => {
                if (cancelled) return;
                let fileName = imgdata.image_file.substring(imgdata.image_file.lastIndexOf('/') + 1) || "scaled-image.png";
                const file = new File([blob], fileName, { lastModified: new Date().getTime(), type: blob.type || "image/png" });
                const objectUrl = URL.createObjectURL(file);
                const img = new Image();

                img.onload = function() {
                    if (cancelled) {
                        URL.revokeObjectURL(objectUrl);
                        return;
                    }
                    setImageWidth(img.width);
                    setImageHeight(img.height);
                    setImage(file);
                    URL.revokeObjectURL(objectUrl);
                };
                img.onerror = function() {
                    URL.revokeObjectURL(objectUrl);
                    if (!cancelled) {
                        setDone(true);
                        setErrorMessage("Unable to read the selected image.");
                        setshowDangerAlert(true);
                    }
                };
                img.src = objectUrl;
            })
            .catch(error => {
                if (cancelled) return;
                setDone(true);
                setErrorMessage(error.message || "Unable to load the selected image.");
                setshowDangerAlert(true);
            });

        return () => {
            cancelled = true;
        };
    }, [scaleshow, imgdata?.image_file])



    const Uploaded = () => {
        if (!scaleimg || !image) {
            setErrorMessage("Please wait for the scaled image preview to finish loading.");
            setshowDangerAlert(true);
            return;
        }

        const uploadData = new FormData();
        var newimg = dataURLtoFile(scaleimg, image.name.split('.')[0] + ".png")

        uploadData.append('image_scale', newimg);
        uploadData.append('scale', Number(scale) * (Number(autoscale) || 1));

        fetch('api/home/', {
            headers: {
                'X-CSRFToken': csrftoken
            },
            method: 'POST',
            body: uploadData,
        })
            .then(res => {
                if (!res.ok) {
                    throw new Error("Upload failed. Please try again.");
                }
                setshowDangerAlert(false);
                setshowSuccessAlert(true);
                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            })
            .catch(error => {
                setErrorMessage(error.message || "Upload failed. Please try again.");
                setshowDangerAlert(true);
            })
    }


    const DraggableCard = ({ children }) => {
        const cardRef = useRef(null);
        useDraggable(cardRef);

        return (
            <div className={image !== undefined && done == true ? "dragcard" : "none"} ref={cardRef}>
            </div>
        );
    };


    const dataURLtoFile = (dataurl, filename) => {
        var arr = dataurl.split(','),
            mime = arr[0].match(/:(.*?);/)[1],
            bstr = atob(arr[1]),
            n = bstr.length,
            u8arr = new Uint8Array(n);
        while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
        }
        return new File([u8arr], filename, { type: mime });
    }


    const resizeFile = (image) => {
        setDone(false);
        Resizer.imageFileResizer(
            image,
            Math.max(1, Math.round(imageWidth * Number(scale))),
            Math.max(1, Math.round(imageHeight * Number(scale))),
            "PNG",
            100,
            0,
            (uri) => {
                setScaleImg(uri);
            },
            "base64",
        );
    };






    useEffect(() => {
        if (image !== undefined && scale !== null && imageWidth && imageHeight) {
            try {
                resizeFile(image)

            } catch (err) {
                console.log(err);
                setDone(true);
                setErrorMessage("Unable to resize the selected image.");
                setshowDangerAlert(true);
            }
        }
    }, [image, scale, imageWidth, imageHeight])




    return (
        <Modal
            {...modalProps}
            size="lg"
            aria-labelledby="contained-modal-title-vcenter"
            centered
            fullscreen={true}
        >
            <Modal.Header closeButton>
                <Modal.Title id="contained-modal-title-vcenter">
                    Rescale Your Image
                </Modal.Title>
            </Modal.Header>
            <Modal.Body>

                <div className="App">
                    <div className="dragcontainer">
                        <DraggableCard />
                    </div>

                    <div>
                        <div className="d-flex justify-content-center sticky">
                            <div className={done == false ? "spinner-border text-danger" : "none"}
                                role="status">
                            </div>
                        </div>

                        <img src={scaleimg} alt="Scaled preview" onLoad={(e) => {
                            setDone(true);
                        }}
                            crossOrigin="anonymous" />
                    </div>

                    <Alert
                        show={showDangerAlert}
                        variant="danger"
                        className="mt-3"
                    >
                        {errorMessage}
                    </Alert>
                    <Alert
                        show={showSuccessAlert}
                        variant="success"
                        className="mt-3"
                    >
                        Image scaled and uploaded successfully.
                    </Alert>
                </div>

            </Modal.Body>
            <Modal.Footer>
                <input type="number" value={scale} data-decimals="2" min="0" max="1" step="0.1" id="customRange3" onChange={(e) => setScale(e.target.value)} />
                <Button type="submit" variant="btn btn-outline-danger" onClick={() => Uploaded()} disabled={scaleimg !== undefined && done == true ? false : true}>Upload</Button>
                <Button onClick={props.onHide}>Close</Button>
            </Modal.Footer>
        </Modal>
    )
}



export default ImageScaling
