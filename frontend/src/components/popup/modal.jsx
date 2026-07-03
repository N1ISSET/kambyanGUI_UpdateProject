import React, {useState, useRef, useEffect} from 'react';
import Modal from "react-bootstrap/Modal";
import "bootstrap/dist/css/bootstrap.min.css";
import Button from 'react-bootstrap/Button';
import axios from 'axios';
import jQuery from "jquery";
import {Alert} from 'react-bootstrap';
import "./modal.css";

const isTiffFile = (file) => /\.(tif|tiff)$/i.test(file?.name || "");

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


function FileUpload(props) {

  var csrftoken = getCookie('csrftoken');

  const [images, setImages] = useState([]);
  const [showDangerAlert, setshowDangerAlert] = useState(false);
  const [showSuccessAlert, setshowSuccessAlert] = useState(false);
  const [done, setDone] = useState(true);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState("");

  const pollUploadJobs = (jobIds) => {
    Promise.all(jobIds.map((jobId) => axios.get(`api/upload-status/?job_id=${jobId}`)))
      .then(responses => {
        const jobs = responses.map((response) => response.data || {});
        const failedJob = jobs.find((job) => job.status === "FAILURE");
        const finishedCount = jobs.filter((job) => job.status === "SUCCESS").length;
        const totalProgress = jobs.reduce((sum, job) => sum + (job.progress || 0), 0);
        const averageProgress = Math.round(totalProgress / Math.max(jobs.length, 1));

        setUploadProgress(averageProgress);

        if (failedJob) {
          setshowDangerAlert(true);
          setUploadStatus(failedJob.error || "Upload failed");
          setDone(true);
          return;
        }

        if (finishedCount === jobs.length) {
          setshowSuccessAlert(true);
          setUploadProgress(100);
          setUploadStatus(`Completed ${jobs.length} image${jobs.length === 1 ? "" : "s"}`);
          setDone(true);
          window.location.reload(2);
          return;
        }

        setUploadStatus(`Processing ${finishedCount}/${jobs.length} image${jobs.length === 1 ? "" : "s"}...`);
        setTimeout(() => pollUploadJobs(jobIds), 1500);
      })
      .catch(error => {
        console.log(error);
        setshowDangerAlert(true);
        setUploadStatus("Unable to check upload status");
        setDone(true);
      });
  }

  const Uploaded = () => {
    const invalidImages = images.filter((selectedImage) => !isTiffFile(selectedImage));
    if (invalidImages.length > 0) {
      setshowDangerAlert(true);
      setUploadStatus("Image uploads only allow .tif or .tiff files.");
      return;
    }

    setDone(false); 
    setUploadProgress(0);
    setUploadStatus("Uploading...");
    setshowDangerAlert(false);
    setshowSuccessAlert(false);
    const uploadData = new FormData();

    images.forEach((selectedImage) => {
      uploadData.append('image_file', selectedImage);
    });
    axios.post('api/resizeIMG/', uploadData, { // receive two parameter endpoint url ,form data 
      headers: {
          'content-type': 'multipart/form-data',
          'X-CSRFToken': csrftoken,
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
  })
      .then(res => {
                    const jobs = res.data && res.data.jobs;
                    const jobIds = Array.isArray(jobs) ? jobs.map((job) => job.id) : [res.data && res.data.id].filter(Boolean);
                    if (jobIds.length > 0) {
                      setUploadStatus(`Queued ${jobIds.length} image${jobIds.length === 1 ? "" : "s"} for processing...`);
                      pollUploadJobs(jobIds);
                    } else {
                      setshowSuccessAlert(true)
                      setUploadProgress(100)
                      setUploadStatus("Completed")
                      window.location.reload(2)
                      setDone(true)
                    }})
      .catch(error => {console.log(error);
        setshowDangerAlert(true)
        setUploadStatus("Upload failed")
        setDone(true)})
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
          Upload Your Image
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        
          <div className="App">
          <div className="input-group mb-3">
              <input type="file" className="form-control" id="images-upload" accept=".tif,.tiff,image/tiff" multiple onChange={(e) => {
                const selectedFiles = Array.from(e.target.files || []);
                const invalidImages = selectedFiles.filter((selectedImage) => !isTiffFile(selectedImage));
                setImages(selectedFiles.filter(isTiffFile));
                setshowDangerAlert(invalidImages.length > 0);
                setUploadStatus(invalidImages.length > 0 ? "Image uploads only allow .tif or .tiff files." : "");
              }}/> 
          </div>

          {done == false && (
            <div className="upload-progress">
              <div className="progress">
                <div
                  className="progress-bar progress-bar-striped progress-bar-animated bg-danger"
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
        Upload completed successfully.
      </Alert>
          </div>
        
      </Modal.Body>
      <Modal.Footer>
      <Button type="submit" variant="btn btn-outline-danger" onClick={() => Uploaded()} disabled={images.length > 0 && done == true ? false : true}>Upload</Button>
        <Button onClick={props.onHide}>Close</Button>
      </Modal.Footer>
    </Modal>
    )
}

export default FileUpload
