import React, { useState, useRef, useEffect} from 'react';
import Modal from "react-bootstrap/Modal";
import "bootstrap/dist/css/bootstrap.min.css";
import Button from 'react-bootstrap/Button';
import axios from 'axios';
import jQuery from "jquery";
import { Alert } from 'react-bootstrap';
import Papa from "papaparse";

const isTiffFile = (file) => /\.(tif|tiff)$/i.test(file?.name || "");
const isCsvFile = (file) => /\.csv$/i.test(file?.name || "");

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


function ReviewUpload(props) {

    var csrftoken = getCookie('csrftoken');

    const [image, setImage] = useState();
    const [csvdata, setCSVdata] = useState([]);
    const [showDangerAlert, setshowDangerAlert] = useState(false);
    const [showSuccessAlert, setshowSuccessAlert] = useState(false);
    const [done, setDone] = useState(true);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [uploadStatus, setUploadStatus] = useState("");
    const [csvFileName, setCsvFileName] = useState("");

    const pollUploadJob = (jobId) => {
        axios.get(`api/upload-status/?job_id=${jobId}`)
            .then(res => {
                const data = res.data || {};
                setUploadProgress(data.progress || 0);
                setUploadStatus(data.message || "Processing on server...");

                if (data.status === "SUCCESS") {
                    setshowSuccessAlert(true);
                    setUploadProgress(100);
                    setUploadStatus("Completed");
                    setDone(true);
                    window.location.reload(2);
                    return;
                }

                if (data.status === "FAILURE") {
                    setshowDangerAlert(true);
                    setUploadStatus(data.error || "Upload failed");
                    setDone(true);
                    return;
                }

                setTimeout(() => pollUploadJob(jobId), 1500);
            })
            .catch(error => {
                setshowDangerAlert(true);
                setUploadStatus("Unable to check upload status");
                setDone(true);
            });
    }

    const Uploaded = async () => {
        if (image !== undefined) {
        if (!isTiffFile(image)) {
            setshowDangerAlert(true)
            setUploadStatus("Image imports only allow .tif or .tiff files.")
            return
        }
        if (!csvFileName || !isCsvFile({ name: csvFileName })) {
            setshowDangerAlert(true)
            setUploadStatus("Plot data imports only allow .csv files.")
            return
        }
        setDone(false);
        setUploadProgress(0);
        setUploadStatus("Uploading...");
        setshowDangerAlert(false);
        setshowSuccessAlert(false);
        let new_data = JSON.stringify(csvdata);
        console.log(new_data)
        
        const uploadData = new FormData();
        
        uploadData.append('image_file', image);
        uploadData.append('csv_data', new_data);
        uploadData.append('csv_file_name', csvFileName);
        let url = "api/reviewdata/";
        await axios
        .post(url, uploadData, {
          // receive two parameter endpoint url ,form data
          headers: {
            "content-type": "multipart/form-data",
            "X-CSRFToken": csrftoken,
            // 'Authorization':`Token ${this.props.token}`
          },
          onUploadProgress: (progressEvent) => {
            if (progressEvent.total) {
              const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
              setUploadProgress(Math.min(percentCompleted, 95));
              if (percentCompleted >= 100) {
                setUploadStatus("Processing on server...");
              }
            }
          },
        }).then(res => {
            const jobId = res.data && res.data.id;
            if (jobId) {
                setUploadStatus("Queued for processing...");
                pollUploadJob(jobId);
            } else {
                setshowSuccessAlert(true)
                setUploadProgress(100)
                setUploadStatus("Completed")
                window.location.reload(2)
            }})
            .catch(error => {
                setshowDangerAlert(true)
                setUploadStatus("Upload failed")
                setDone(true)
            })
    }
    }
    const handleCSV = (e) => {
        const files = e.target.files;
        console.log(files);
        const selectedFile = files && files[0];
        if (selectedFile && !isCsvFile(selectedFile)) {
            setCSVdata([]);
            setCsvFileName("");
            setshowDangerAlert(true);
            setUploadStatus("Plot data imports only allow .csv files.");
            return;
        }
        if (selectedFile) {
            setCsvFileName(selectedFile.name);
            setshowDangerAlert(false);
            setUploadStatus("");
            Papa.parse(selectedFile, {
                complete: function (results) {
                    setCSVdata(results.data.slice(1));
                }
            }
            )
        }
    }




    return (
        <Modal
            {...props}
            size="lg"
            aria-labelledby="contained-modal-title-vcenter"
            centered
        >
            <Modal.Header closeButton>
                <Modal.Title id="contained-modal-title-vcenter">
                    Upload Your Image and Coordinate CSV
                </Modal.Title>
            </Modal.Header>
            <Modal.Body>
                    <div className="App">
                        <div className="upload-file-field mb-3">
                            <label htmlFor="images-upload">Upload image</label>
                            <input type="file" className="form-control" id="images-upload" accept=".tif,.tiff,image/tiff" onChange={(e) => {
                                const selectedFile = e.target.files[0];
                                if (selectedFile && !isTiffFile(selectedFile)) {
                                    setImage(undefined);
                                    setshowDangerAlert(true);
                                    setUploadStatus("Image imports only allow .tif or .tiff files.");
                                    return;
                                }
                                setImage(selectedFile);
                                setshowDangerAlert(false);
                                setUploadStatus("");
                            }}/> 
                        </div>
                        <div className="upload-file-field mb-3">
                            <label htmlFor="csv-upload">Upload coordinate CSV</label>
                            <input type="file" className="form-control" id="csv-upload" accept=".csv" onChange={handleCSV}/>
                        </div>


                        {done == false && (
                            <div className="upload-progress">
                                <div className="progress">
                                    <div
                                        className="progress-bar progress-bar-striped progress-bar-animated bg-secondary"
                                        role="progressbar"
                                        style={{ width: `${uploadProgress}%` }}
                                        aria-valuenow={uploadProgress}
                                        aria-valuemin="0"
                                        aria-valuemax="100"
                                    >
                                        {uploadProgress}%
                                    </div>
                                </div>
                                <div className="upload-progress-status">{uploadStatus}</div>
                            </div>
                        )}
                        
                        <Alert
                            show={showDangerAlert}
                            variant="danger"
                            className="mt-3"
                        >
                            {uploadStatus || "Upload failed. Please try again."}
                        </Alert>
                        <Alert
                            show={showSuccessAlert}
                            variant="success"
                            className="mt-3"
                        >
                            Import completed successfully.
                        </Alert>
                    </div>
            </Modal.Body>
            <Modal.Footer>
            <Button type="submit" variant="btn btn-outline-danger" onClick={() => Uploaded()} disabled={image !== undefined && csvFileName && done == true? false : true}>Upload</Button>
                <Button onClick={props.onHide}>Close</Button>
            </Modal.Footer>
        </Modal>
    )
}

export default ReviewUpload
