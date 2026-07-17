import React, { useState, useCallback, useRef } from "react";
import { MapContainer, ImageOverlay, ZoomControl } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-markercluster";
import { CRS } from "leaflet";
import * as L from "leaflet";
import AddMarker from "../AddMarker";
import "./MapKambyan.css";
import axios from "axios";
import { useEffect } from "react";
import FileUpload from "../popup/modal";
import ReviewUpload from "../popup/ReviewModal";
import GenerateFlag from "../popup/GenerateModal";
import AssignFlag from "../popup/AssignModal";
import ImageScaling from "../popup/ScaleModal";
import * as AiIcon from "react-icons/ai";
import * as MdIcon from "react-icons/md";
import * as FaIcon from "react-icons/fa";
import ReactLoading from "react-loading";
import jQuery from "jquery";

const DETECTION_JOB_STORAGE_KEY = "kambyanDetectionJobIds";
const LEGACY_DETECTION_JOB_STORAGE_KEY = "kambyanDetectionJobId";
const EXPORT_JOB_STORAGE_KEY = "kambyanExportJobIds";
const EXPORT_READY_STORAGE_KEY = "kambyanSessionExportReadyJobs";

function isDetectionJobActive(job) {
  return job && (job.status === "PENDING" || job.status === "STARTED");
}

function isExportJobActive(job) {
  return job && (job.status === "PENDING" || job.status === "STARTED");
}

function getStoredDetectionJobIds() {
  const storedJobIds = localStorage.getItem(DETECTION_JOB_STORAGE_KEY);
  if (storedJobIds) {
    try {
      const parsedJobIds = JSON.parse(storedJobIds);
      if (Array.isArray(parsedJobIds)) {
        return parsedJobIds.filter(Boolean);
      }
    } catch (error) {
      return [];
    }
  }

  const legacyJobId = localStorage.getItem(LEGACY_DETECTION_JOB_STORAGE_KEY);
  return legacyJobId ? [legacyJobId] : [];
}

function storeDetectionJobIds(jobIds) {
  const uniqueJobIds = Array.from(new Set(jobIds.filter(Boolean).map(String)));
  if (uniqueJobIds.length > 0) {
    localStorage.setItem(DETECTION_JOB_STORAGE_KEY, JSON.stringify(uniqueJobIds));
  } else {
    localStorage.removeItem(DETECTION_JOB_STORAGE_KEY);
  }
  localStorage.removeItem(LEGACY_DETECTION_JOB_STORAGE_KEY);
}

function getStoredExportJobIds() {
  localStorage.removeItem(EXPORT_JOB_STORAGE_KEY);
  const storedJobIds = sessionStorage.getItem(EXPORT_JOB_STORAGE_KEY);
  if (!storedJobIds) return [];

  try {
    const parsedJobIds = JSON.parse(storedJobIds);
    return Array.isArray(parsedJobIds) ? parsedJobIds.filter(Boolean) : [];
  } catch (error) {
    return [];
  }
}

function storeExportJobIds(jobIds) {
  const uniqueJobIds = Array.from(new Set(jobIds.filter(Boolean).map(String)));
  if (uniqueJobIds.length > 0) {
    sessionStorage.setItem(EXPORT_JOB_STORAGE_KEY, JSON.stringify(uniqueJobIds));
  } else {
    sessionStorage.removeItem(EXPORT_JOB_STORAGE_KEY);
  }
  localStorage.removeItem(EXPORT_JOB_STORAGE_KEY);
}

function getStoredReadyExportJobs() {
  const storedJobs = sessionStorage.getItem(EXPORT_READY_STORAGE_KEY);
  if (!storedJobs) return [];

  try {
    const parsedJobs = JSON.parse(storedJobs);
    if (!Array.isArray(parsedJobs)) return [];

    return parsedJobs.filter(
      (job) => job && job.image_id && job.status === "SUCCESS" && job.artifact_exists === true
    );
  } catch (error) {
    return [];
  }
}

function storeReadyExportJobs(jobs) {
  const readyJobs = jobs.filter(
    (job) => job && job.image_id && job.status === "SUCCESS" && job.artifact_exists === true
  );

  if (readyJobs.length > 0) {
    sessionStorage.setItem(EXPORT_READY_STORAGE_KEY, JSON.stringify(readyJobs));
  } else {
    sessionStorage.removeItem(EXPORT_READY_STORAGE_KEY);
  }
}

function getCookie(name) {
  var cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    var cookies = document.cookie.split(";");
    for (var i = 0; i < cookies.length; i++) {
      var cookie = jQuery.trim(cookies[i]);
      if (cookie.substring(0, name.length + 1) === name + "=") {
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
    // Keep local backend media on the same Vite origin so the dev proxy
    // retrieves it from Django on the host machine.
    if (isLocalBackend) {
      return `${parsedUrl.pathname}${parsedUrl.search}`;
    }

    return parsedUrl.href;
  } catch (error) {
    return url;
  }
}

function MapKambyan({
  currentUser,
  onLogout,
  isAdmin = false,
  showAdminPanel = false,
  onToggleAdminPanel,
  children,
}) {
  const url_api = "api/home/";
  const [dataImage, setDataImage] = useState({});
  const [imageList, setImageList] = useState([]);
  // const [classChange, setClassChange] = useState(false);
  const [modalShow, setModalShow] = React.useState(false);
  const [scaleShow, setScaleShow] = React.useState(false);
  const [generateShow, setGenerateShow] = React.useState(false);
  const [assignShow, setAssignShow] = React.useState(false);
  const [reviewShow, setReviewShow] = React.useState(false);
  const [coord, setCoord] = useState([]);
  const [done, setDone] = useState("not");
  const [scale, setScale] = useState();
  const [scaleMeta, setScaleMeta] = useState(null);
  const [imgMeta, setImgMeta] = useState(null);
  const [metatxt, setMetatxt] = useState();
  const [processProgress, setProcessProgress] = useState(0);
  const [processLabel, setProcessLabel] = useState("Processing");
  const [detectionJobs, setDetectionJobs] = useState([]);
  const [exportJobs, setExportJobs] = useState([]);
  const [sessionReadyExportJobs, setSessionReadyExportJobs] = useState(getStoredReadyExportJobs);
  const [markerRefreshKey, setMarkerRefreshKey] = useState(0);
  const [showImageNotification, setShowImageNotification] = useState(true);
  const [notification, setNotification] = useState(null);
  const [exportTooltip, setExportTooltip] = useState({ visible: false, x: 0, y: 0 });
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const mapRef = useRef(null);
  const activeDetectionJobIdsRef = useRef(new Set());
  const dismissedDetectionJobIdsRef = useRef(new Set());
  const activeExportJobIdsRef = useRef(new Set());
  const dismissedExportJobIdsRef = useRef(new Set());

  const childToParent = useCallback((childdata) => {
    setCoord(childdata);
  }, []);

  const showNotification = useCallback((title, message, type = "success") => {
    setNotification({ title, message, type });
  }, []);

  const closeNotification = useCallback(() => {
    setNotification(null);
  }, []);

  const refreshCurrentMarkers = useCallback(() => {
    setMarkerRefreshKey((currentKey) => currentKey + 1);
  }, []);

  const removeReadyExportJobForImage = useCallback((imageId) => {
    if (!imageId) return;
    setSessionReadyExportJobs((currentJobs) => {
      const nextJobs = currentJobs.filter((job) => String(job.image_id) !== String(imageId));
      storeReadyExportJobs(nextJobs);
      return nextJobs;
    });
  }, []);

  const rememberReadyExportJob = useCallback((job) => {
    if (!job || job.status !== "SUCCESS" || job.artifact_exists !== true) return;
    setSessionReadyExportJobs((currentJobs) => {
      const nextJobs = [
        job,
        ...currentJobs.filter((currentJob) => String(currentJob.image_id) !== String(job.image_id)),
      ];
      storeReadyExportJobs(nextJobs);
      return nextJobs;
    });
  }, []);

  const upsertDetectionJob = useCallback((job) => {
    if (!job || !job.id) return;
    setDetectionJobs((currentJobs) => {
      const jobId = String(job.id);
      const existingJob = currentJobs.find((currentJob) => String(currentJob.id) === jobId);
      const remainingJobs = currentJobs.filter((currentJob) => String(currentJob.id) !== jobId);
      const nextJobs = existingJob
        ? currentJobs.map((currentJob) => (String(currentJob.id) === jobId ? job : currentJob))
        : [job, ...remainingJobs];
      storeDetectionJobIds(nextJobs.map((currentJob) => currentJob.id));
      return nextJobs;
    });
  }, []);

  const fetchDetectionJob = useCallback(async (jobId) => {
    const response = await axios.get(`/api/processimg/?job_id=${encodeURIComponent(jobId)}`);
    const job = response.data;
    if (!dismissedDetectionJobIdsRef.current.has(String(job.id))) {
      upsertDetectionJob(job);
    }
    return job;
  }, [upsertDetectionJob]);

  const upsertExportJob = useCallback((job) => {
    if (!job || !job.id) return;
    setExportJobs((currentJobs) => {
      const jobId = String(job.id);
      const existingJob = currentJobs.find((currentJob) => String(currentJob.id) === jobId);
      const remainingJobs = currentJobs.filter((currentJob) => String(currentJob.id) !== jobId);
      const nextJobs = existingJob
        ? currentJobs.map((currentJob) => (String(currentJob.id) === jobId ? job : currentJob))
        : [job, ...remainingJobs];
      storeExportJobIds(nextJobs.map((currentJob) => currentJob.id));
      return nextJobs;
    });
  }, []);

  const fetchExportJob = useCallback(async (jobId) => {
    const response = await axios.get(`/api/assignID/?job_id=${encodeURIComponent(jobId)}`);
    const job = response.data;
    if (!dismissedExportJobIdsRef.current.has(String(job.id))) {
      upsertExportJob(job);
    }
    rememberReadyExportJob(job);
    return job;
  }, [rememberReadyExportJob, upsertExportJob]);

  const activeDetectionJobIds = detectionJobs
    .filter(isDetectionJobActive)
    .map((job) => job.id)
    .join(",");

  const activeExportJobIds = exportJobs
    .filter(isExportJobActive)
    .map((job) => job.id)
    .join(",");

  const currentProgressExportJob = dataImage.id
    ? exportJobs.find((job) => String(job.image_id) === String(dataImage.id))
    : null;
  const currentReadyExportJob = dataImage.id
    ? sessionReadyExportJobs.find((job) => String(job.image_id) === String(dataImage.id))
    : null;
  const currentExportJob = currentProgressExportJob || currentReadyExportJob;
  const exportZipUrl = currentExportJob?.zip_url ? getProxiedMediaUrl(currentExportJob.zip_url) : "";
  const canExportResult = currentReadyExportJob?.status === "SUCCESS" && currentReadyExportJob?.artifact_exists === true;

  const showExportUnavailableTooltip = useCallback((event) => {
    if (canExportResult) return;
    setExportTooltip({
      visible: true,
      x: event.clientX,
      y: event.clientY,
    });
  }, [canExportResult]);

  const moveExportUnavailableTooltip = useCallback((event) => {
    if (canExportResult) return;
    setExportTooltip((currentTooltip) => ({
      ...currentTooltip,
      visible: true,
      x: event.clientX,
      y: event.clientY,
    }));
  }, [canExportResult]);

  const hideExportUnavailableTooltip = useCallback(() => {
    setExportTooltip((currentTooltip) => ({
      ...currentTooltip,
      visible: false,
    }));
  }, []);

  // State for image dimensions (loaded asynchronously)
  const [imgDimensions, setImgDimensions] = useState(null);
  const [imgSrc, setImgSrc] = useState(null);
  const hasUploadedImage = Boolean(dataImage.image_file);

  const displayedImageName = imgSrc
    ? decodeURIComponent(imgSrc.split("/").pop() || "Selected image")
    : "";

  useEffect(() => {
    const resizeTimer = setTimeout(() => {
      mapRef.current?.invalidateSize();
    }, 260);

    return () => clearTimeout(resizeTimer);
  }, [isSidebarCollapsed, imgDimensions]);

  // Parallelize all API calls on mount (use allSettled so one failure doesn't block the rest)
  useEffect(() => {
    const fetchData = async () => {
      const results = await Promise.allSettled([
        axios.get(url_api),
        axios.get("/api/imgmetadata/"),
        axios.get("/api/metatxt/"),
      ]);

      // Home / image data
      if (results[0].status === 'fulfilled') {
        const data1 = results[0].value.data;
        setImageList(Array.isArray(data1) ? data1 : []);
        if (data1 && data1.length > 0) {
          setDataImage(data1[data1.length - 1]);
        }
      } else {
        console.error("Failed to fetch home data:", results[0].reason);
      }

      if (results[1].status === 'fulfilled') {
        const metaData = results[1].value.data;
        if (metaData && metaData[0]) {
          setImgMeta(metaData[0]);
        }
      } else {
        console.error("Failed to fetch image metadata:", results[1].reason);
      }

      // Meta text
      if (results[2].status === 'fulfilled') {
        const metatxtData = results[2].value.data;
        if (metatxtData && metatxtData['message']) {
          setMetatxt(metatxtData['message']);
        }
      } else {
        console.error("Failed to fetch metatxt:", results[2].reason);
      }
    };
    fetchData();
  }, []);

  useEffect(() => {
    if (!dataImage.id) {
      setScale(undefined);
      setScaleMeta(null);
      return;
    }

    let cancelled = false;
    axios
      .get(`/api/scaledata/?image_id=${encodeURIComponent(dataImage.id)}`)
      .then((response) => {
        if (cancelled) return;
        const scaleData = response.data;
        const selectedScale = Array.isArray(scaleData)
          ? scaleData.find((item) => String(item.image) === String(dataImage.id))
          : scaleData;
        const resolvedScale = selectedScale
          ? selectedScale
          : {
              scale: dataImage.preview_scale_x || 1,
              scale_x: dataImage.preview_scale_x || 1,
              scale_y: dataImage.preview_scale_y || 1,
              detection_scale_x: dataImage.detection_scale_x || 1,
              detection_scale_y: dataImage.detection_scale_y || 1,
            };
        setScale(resolvedScale.scale);
        setScaleMeta(resolvedScale);
      })
      .catch((error) => {
        if (!cancelled) {
          console.error("Failed to fetch scale data:", error);
          const fallbackScale = dataImage.preview_scale_x || 1;
          setScale(fallbackScale);
          setScaleMeta({
            scale: fallbackScale,
            scale_x: dataImage.preview_scale_x || fallbackScale,
            scale_y: dataImage.preview_scale_y || fallbackScale,
            detection_scale_x: dataImage.detection_scale_x || 1,
            detection_scale_y: dataImage.detection_scale_y || 1,
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [dataImage]);

  useEffect(() => {
    const storedNotification = sessionStorage.getItem("detectionFinishedNotification");
    if (!storedNotification) return;

    sessionStorage.removeItem("detectionFinishedNotification");
    try {
      const parsedNotification = JSON.parse(storedNotification);
      showNotification(
        parsedNotification.title || "Detection finished",
        parsedNotification.message || "Detection has been completed."
      );
    } catch (error) {
      showNotification("Detection finished", "Detection has been completed.");
    }
  }, [showNotification]);

  useEffect(() => {
    const storedJobIds = getStoredDetectionJobIds();
    if (storedJobIds.length === 0) return;

    storedJobIds.forEach((storedJobId) => {
      fetchDetectionJob(storedJobId).catch(() => {
        const remainingStoredJobIds = getStoredDetectionJobIds()
          .filter((jobId) => String(jobId) !== String(storedJobId));
        storeDetectionJobIds(remainingStoredJobIds);
      });
    });
  }, [fetchDetectionJob]);

  useEffect(() => {
    const storedJobIds = getStoredExportJobIds();
    if (storedJobIds.length === 0) return;

    storedJobIds.forEach((storedJobId) => {
      fetchExportJob(storedJobId).catch(() => {
        const remainingStoredJobIds = getStoredExportJobIds()
          .filter((jobId) => String(jobId) !== String(storedJobId));
        storeExportJobIds(remainingStoredJobIds);
      });
    });
  }, [fetchExportJob]);

  useEffect(() => {
    if (!activeDetectionJobIds) return undefined;

    const progressTimer = setInterval(() => {
      activeDetectionJobIds.split(",").forEach((jobId) => {
        fetchDetectionJob(jobId).catch((error) => {
          console.error("Failed to fetch detection progress:", error);
        });
      });
    }, 2000);

    return () => clearInterval(progressTimer);
  }, [activeDetectionJobIds, fetchDetectionJob]);

  useEffect(() => {
    if (!activeExportJobIds) return undefined;

    const progressTimer = setInterval(() => {
      activeExportJobIds.split(",").forEach((jobId) => {
        fetchExportJob(jobId).catch((error) => {
          console.error("Failed to fetch export progress:", error);
        });
      });
    }, 2000);

    return () => clearInterval(progressTimer);
  }, [activeExportJobIds, fetchExportJob]);

  useEffect(() => {
    detectionJobs.forEach((job) => {
      const jobId = String(job.id);

      if (isDetectionJobActive(job)) {
        activeDetectionJobIdsRef.current.add(jobId);
        return;
      }

      if (!activeDetectionJobIdsRef.current.has(jobId)) return;

      activeDetectionJobIdsRef.current.delete(jobId);

      if (job.status === "SUCCESS") {
        refreshCurrentMarkers();
        showNotification(
          "Detection finished",
          "Detection has been completed successfully."
        );
      }

      if (job.status === "FAILURE") {
        showNotification(
          "Detection failed",
          job.error || "Detection could not be completed. Please try again.",
          "error"
        );
      }
    });
  }, [detectionJobs, refreshCurrentMarkers, showNotification]);

  useEffect(() => {
    exportJobs.forEach((job) => {
      const jobId = String(job.id);

      if (isExportJobActive(job)) {
        activeExportJobIdsRef.current.add(jobId);
        return;
      }

      if (!activeExportJobIdsRef.current.has(jobId)) return;
      activeExportJobIdsRef.current.delete(jobId);

      if (job.status === "SUCCESS") {
        showNotification(
          "Export files ready",
          "Tree IDs, map coordinates, annotations, and export files are ready."
        );
      }

      if (job.status === "FAILURE") {
        showNotification(
          "Save data failed",
          job.error || "Export files could not be prepared. Please try again.",
          "error"
        );
      }
    });
  }, [dataImage.id, exportJobs, showNotification]);

  // Async image dimension loading — runs once when dataImage changes
  useEffect(() => {
    setImgDimensions(null);
    setImgSrc(null);
    if (!dataImage.image_file) return;
    const img = new window.Image();
    img.onload = () => {
      setImgDimensions({ height: img.height, width: img.width });
      setImgSrc(img.src);
      setShowImageNotification(true);
    };
    img.src = getProxiedMediaUrl(dataImage.image_file);
  }, [dataImage.image_file]);

  const handleImageSelection = (event) => {
    const selectedImage = imageList.find((image) => String(image.id) === event.target.value);
    if (selectedImage) {
      setDataImage(selectedImage);
      setShowImageNotification(true);
    }
  };

  useEffect(() => {
    if (done !== "done") return;

    const progressTimer = setInterval(() => {
      setProcessProgress((currentProgress) => {
        if (currentProgress >= 95) return currentProgress;
        const nextStep = currentProgress < 70 ? 5 : 2;
        return Math.min(currentProgress + nextStep, 95);
      });
    }, 700);

    return () => clearInterval(progressTimer);
  }, [done]);

  // Derive bounds and center only when dimensions are available
  const bounds = imgDimensions
    ? L.latLngBounds([[0, 0], [imgDimensions.height, imgDimensions.width]])
    : null;
  const center = imgDimensions
    ? L.latLng(imgDimensions.height / 2, imgDimensions.width / 2)
    : L.latLng(0, 0);
  // update center auto ?

  const handleDetect = async () => {
    setProcessLabel("Start detection");
    setProcessProgress(0);
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }
    var csrftoken = getCookie("csrftoken");
    const path_vid = new FormData();
    path_vid.append("image_id", dataImage.id);
    path_vid.append("datetime", dataImage.uploaded_on);
    let url = "/api/processimg/";
    await axios
      .post(url, path_vid, {
        // receive two parameter endpoint url ,form data
        headers: {
          "content-type": "multipart/form-data",
          "X-CSRFToken": csrftoken,
          // 'Authorization':`Token ${this.props.token}`
        },
      })
      .then((res) => {
        const job = res.data;
        dismissedDetectionJobIdsRef.current.delete(String(job.id));
        upsertDetectionJob(job);
        setProcessLabel(job.message || "Start detection");
        setProcessProgress(job.progress || 0);
        showNotification(
          "Detection started",
          "Detection is running in the background."
        );
      })
      .catch((error) => {
        const backendMessage = error.response?.data?.error || error.response?.data?.message;
        console.error("Start detection failed:", backendMessage || error);
        setProcessProgress(0);
        showNotification(
          "Detection failed",
          backendMessage || "Detection could not be completed. Please try again.",
          "error"
        );
      });
  };

  const handleRemovePlots = async () => {
    if (!dataImage.id) {
      showNotification(
        "No image selected",
        "Select a plantation image before removing plots.",
        "error"
      );
      return;
    }

    if (!window.confirm("Remove all plotted points from the selected image?")) {
      return;
    }

    try {
      await axios.delete("/api/tempdata/", {
        data: { image_id: dataImage.id },
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
      });
      setCoord([]);
      refreshCurrentMarkers();
      showNotification("Plots removed", "All plotted points have been cleared.");
    } catch (error) {
      console.error("Remove plots failed:", error);
      showNotification(
        "Could not remove plots",
        error.response?.data?.error || "Please try again.",
        "error"
      );
    }
  };

  const closeDetectionTask = useCallback((jobId) => {
    dismissedDetectionJobIdsRef.current.add(String(jobId));
    setDetectionJobs((currentJobs) => {
      const nextJobs = currentJobs.filter((job) => String(job.id) !== String(jobId));
      storeDetectionJobIds(nextJobs.map((job) => job.id));
      return nextJobs;
    });
    activeDetectionJobIdsRef.current.delete(String(jobId));
  }, []);

  const handleAssign = async () => {

    if (coord.length !== 0) {
      setProcessLabel("Saving data");
      setProcessProgress(0);
      removeReadyExportJobForImage(dataImage.id);
      var csrftoken = getCookie("csrftoken");
      const list_coor = new FormData();
      let new_data = [];
      for (let i = 0; i < coord.length; i++) {
        new_data.push({ X_coord: coord[i].lng, Y_coord: coord[i].lat });
      }
      new_data = JSON.stringify(new_data);

      list_coor.append("coordinate", new_data);
      list_coor.append("datetime", dataImage.uploaded_on);
      list_coor.append('image_id', dataImage.id);
      list_coor.append('image_file', dataImage.image_file);
      list_coor.append('img_height', dataImage.image_height);
      list_coor.append('image_width', dataImage.image_width);
      list_coor.append('scale', scale);
      let url = "/api/assignID/";
      await axios
        .post(url, list_coor, {
          // receive two parameter endpoint url ,form data
          headers: {
            "content-type": "multipart/form-data",
            "X-CSRFToken": csrftoken,
            // 'Authorization':`Token ${this.props.token}`
          },
        })
        .then((res) => {
          const job = res.data;
          if (job) {
            dismissedExportJobIdsRef.current.delete(String(job.id));
            upsertExportJob(job);
            rememberReadyExportJob(job);
            setProcessLabel(job.message || "Preparing export files");
            setProcessProgress(job.progress || 0);
            showNotification(
              "Save data started",
              "Export files are being prepared in the background."
            );
          }
        })
        .catch((error) => {
          console.error("Save data failed:", error);
          setProcessProgress(0);
          showNotification(
            "Save data failed",
            error.response?.data?.error || "Data could not be saved. Please try again.",
            "error"
          );
        });

    }

    else {
      setAssignShow(true)
    }

  };

  const url_plotCoord = "/api/test/";
  const url_annotateData = "/api/test2/";

  const closeExportTask = useCallback((jobId) => {
    dismissedExportJobIdsRef.current.add(String(jobId));
    setExportJobs((currentJobs) => {
      const nextJobs = currentJobs.filter((job) => String(job.id) !== String(jobId));
      storeExportJobIds(nextJobs.map((job) => job.id));
      return nextJobs;
    });
    activeExportJobIdsRef.current.delete(String(jobId));
  }, []);


  const test3 = imgSrc || '';
  const test4 = test3.split("/");
  const last = test4[test4.length - 1] || '';
  const last1 = last.split(".")[0]
  const imageDirectory = test3.substring(0, test3.lastIndexOf("/"));

  const url_imageTile = exportZipUrl || (imageDirectory ? getProxiedMediaUrl(imageDirectory + '/zip/' + last1 + '.zip') : '')

  const escapeCsvValue = (value) => {
    if (value === null || value === undefined) return "";
    const stringValue = String(value);
    if (/[",\r\n]/.test(stringValue)) {
      return `"${stringValue.replace(/"/g, '""')}"`;
    }
    return stringValue;
  };

  const downloadBlob = (blob, filename) => {
    const element = document.createElement("a");
    element.href = URL.createObjectURL(blob);
    element.download = filename;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
    setTimeout(() => URL.revokeObjectURL(element.href), 0);
  };

  const downloadCsvFile = (rows, headers, filename) => {
    const headerLabels = headers.map((header) => header.label);
    const csvRows = [
      headerLabels.map(escapeCsvValue).join(","),
      ...rows.map((row) =>
        headers.map((header) => escapeCsvValue(row[header.key])).join(",")
      ),
    ];
    const blob = new Blob([csvRows.join("\r\n")], { type: "text/csv;charset=utf-8;" });
    downloadBlob(blob, filename);
  };

  const downloadFile = async () => {
    if (!url_imageTile) return;
    const response = await axios.get(url_imageTile, { responseType: "blob" });
    const blob = new Blob([response.data], { type: response.headers["content-type"] || "application/zip" });
    downloadBlob(blob, `${last1}.zip`);
  }

  const downloadTxtFile = () => {
    const file = new Blob([metatxt], {
      type: "text/plain"
    });
    downloadBlob(file, `${String(dataImage.image_file).split("/")[String(dataImage.image_file).split("/").length - 1].split('.')[0]}_Metadata.txt`);
  };

  const download = async () => {
    if (!canExportResult) {
      setGenerateShow(true);
      return;
    }

    try {
      const [coordinateResponse, annotateResponse] = await Promise.all([
        axios.get(url_plotCoord),
        axios.get(url_annotateData),
      ]);

      const coordinateRows = Array.isArray(coordinateResponse.data) ? coordinateResponse.data : [];
      const annotateRows = Array.isArray(annotateResponse.data) ? annotateResponse.data : [];

      if (coordinateRows.length === 0) {
        setGenerateShow(true);
        return;
      }

      downloadCsvFile(coordinateRows, headers, `${last1}_Coordinate.csv`);
      downloadCsvFile(annotateRows, headers2, `${last1}_Annotate.csv`);
      await downloadFile();
      downloadTxtFile();
    } catch (error) {
      console.error("Export result failed:", error);
      setGenerateShow(true);
    }
  };

  let headers = [
    { label: "ID", key: "ids" },
    { label: "X Coordinate", key: "X_Coordinate" },
    { label: "Y Coordinate", key: "Y_Coordinate" },
    { label: "Scale", key: "Scale" },
    { label: "X Pixel", key: "X_Pixel" },
    { label: "Y Pixel", key: "Y_Pixel" },
  ];

  let headers2 = [
    { label: "filename", key: "filename" },
    { label: "width", key: "width" },
    { label: "height", key: "height" },
    { label: "class", key: "classes" },
    { label: "xmin", key: "xmin" },
    { label: "ymin", key: "ymin" },
    { label: "xmax", key: "xmax" },
    { label: "ymax", key: "ymax" },
  ];

  const hasOpenModal = modalShow || scaleShow || generateShow || assignShow || reviewShow;
  const createClusterIcon = (cluster) => {
    const childCount = cluster.getChildCount();
    const clusterTone = childCount < 10 ? "green" : "yellow";

    return L.divIcon({
      html: `<div><span>${childCount}</span></div>`,
      className: `marker-cluster marker-cluster-${clusterTone}`,
      iconSize: L.point(40, 40),
    });
  };

  return (
    <div className={`home ${isSidebarCollapsed ? "sidebar-collapsed" : ""} ${showAdminPanel ? "admin-management-mode" : ""}`}>
      {done === "done" ? (
        <div className="loading-screen">
          <div className="loading-child">
            <div className="processing-panel" role="status" aria-live="polite">
              <div className="processing-title">{processLabel}</div>
              <div className="processing-percent">{processProgress}%</div>
              <div className="progress-bar-track" aria-label={`${processLabel} progress`}>
                <div
                  className="progress-bar-fill"
                  style={{ width: `${processProgress}%` }}
                />
              </div>
              <div className="processing-caption">Please wait while the image is processed.</div>
            </div>
          </div>
        </div>
      ) : null}
      {!hasOpenModal && !showAdminPanel ? (
        <button
          type="button"
          className="sidebar-toggle"
          aria-label={isSidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
          title={isSidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
          onClick={() => setIsSidebarCollapsed((collapsed) => !collapsed)}
        >
          {isSidebarCollapsed ? <MdIcon.MdMenu /> : <MdIcon.MdMenuOpen />}
        </button>
      ) : null}
      {!showAdminPanel ? (
      <div className="content-home-menu">
        <FileUpload show={modalShow} onHide={() => setModalShow(false)} />
        <ImageScaling show={scaleShow} onHide={() => setScaleShow(false)} imgdata={dataImage} autoscale={scale} scaleshow={scaleShow} />
        <AssignFlag show={assignShow} onHide={() => setAssignShow(false)} />
        <ReviewUpload show={reviewShow} onHide={() => setReviewShow(false)} />
        <GenerateFlag show={generateShow} onHide={() => setGenerateShow(false)} />
        <ul className="menu-list">
          <li id="logo-menu">🌴 Kambyan</li>

          {imageList.length > 0 ? (
            <li className="plantation-selector">
              <label htmlFor="plantation-image-select">Plantation Image</label>
              <select
                id="plantation-image-select"
                value={dataImage.id || ""}
                onChange={handleImageSelection}
              >
                {imageList.map((image, index) => {
                  const imageName = image.image_file
                    ? decodeURIComponent(image.image_file.split("/").pop() || `Plantation ${index + 1}`)
                    : `Plantation ${index + 1}`;
                  return (
                    <option key={image.id} value={image.id}>
                      {imageName}
                    </option>
                  );
                })}
              </select>
            </li>
          ) : null}

          <div className="sidebar-divider" />
          <li id="logo-menu">Actions</li>

          <button className="menu upload" onClick={() => setModalShow(true)}>
            <div className="menu-icon">
              <AiIcon.AiOutlineCloudUpload />
            </div>
            <div className="menu-title">Upload</div>
          </button>

          <button className="menu upload" onClick={() => setScaleShow(true)}>
            <div className="menu-icon">
              <MdIcon.MdAspectRatio />
            </div>
            <div className="menu-title">Scale Image</div>
          </button>

          <button className="menu plot" onClick={handleDetect}>
            <div className="menu-icon">
              <MdIcon.MdOutlineScatterPlot />
            </div>
            <div className="menu-title">Start Detection</div>
          </button>

          <button
            type="button"
            className="menu remove-plots"
            onClick={handleRemovePlots}
            disabled={!dataImage.id}
            title="Remove all plotted points from the selected image"
          >
            <div className="menu-icon">
              <MdIcon.MdDeleteSweep />
            </div>
            <div className="menu-title">Remove Plots</div>
          </button>

          <button className="menu assign-id word-save" onClick={handleAssign}>
            <div className="menu-icon">
              <FaIcon.FaSave />
            </div>
            <div className="menu-title">Save Data</div>
          </button>
          <div
            className="export-tooltip-anchor"
            onMouseEnter={showExportUnavailableTooltip}
            onMouseMove={moveExportUnavailableTooltip}
            onMouseLeave={hideExportUnavailableTooltip}
          >
            <button
              type="button"
              className="menu generate-csv"
              onClick={download}
              disabled={!canExportResult}
              title={canExportResult ? "Export result" : undefined}
            >
              <div className="menu-icon">
                <FaIcon.FaFileCsv />
              </div>
              <div className="menu-title">Export Result</div>
            </button>
          </div>

          <button className="menu upload" onClick={() => setReviewShow(true)}>
            <div className="menu-icon">
              <MdIcon.MdFactCheck />
            </div>
            <div className="menu-title">Import Data</div>
          </button>

          {isAdmin ? (
            <button
              className={`menu admin-management ${showAdminPanel ? "active" : ""}`}
              onClick={onToggleAdminPanel}
            >
              <div className="menu-icon">
                <MdIcon.MdAdminPanelSettings />
              </div>
              <div className="menu-title">Management</div>
            </button>
          ) : null}

          <div className="sidebar-divider" />

          <div className="tree-count-card">
            <div className="tree-count-label">Tree Count</div>
            <div className="tree-count-value">{coord.length}</div>
          </div>

          <button className="menu logout" onClick={onLogout}>
            <div className="menu-icon">
              <FaIcon.FaSignOutAlt />
            </div>
            <div className="menu-title">Logout</div>
          </button>

          {currentUser ? (
            <li className="current-user">
              <span className="user-avatar">{currentUser.charAt(0).toUpperCase()}</span>
              {currentUser}
            </li>
          ) : null}
        </ul>
      </div>
      ) : null}
      <div className="content-home-content">
        {showAdminPanel ? (
          <div className="admin-content-view">
            {children}
          </div>
        ) : (
          <>
        {notification ? (
          <div
            className={`app-notification app-notification-${notification.type}`}
            role="status"
            aria-live="polite"
          >
            <div className="app-notification-icon">
              {notification.type === "error" ? <MdIcon.MdErrorOutline /> : <MdIcon.MdCheckCircle />}
            </div>
            <div className="app-notification-text">
              <div className="app-notification-title">{notification.title}</div>
              <div className="app-notification-message">{notification.message}</div>
            </div>
            <button
              type="button"
              className="app-notification-close"
              aria-label="Close notification"
              title="Close"
              onClick={closeNotification}
            >
              <MdIcon.MdClose />
            </button>
          </div>
        ) : null}
        {detectionJobs.length > 0 || exportJobs.length > 0 ? (
          <div className="detection-task-list" aria-live="polite">
            {detectionJobs.map((job) => {
              const jobProgress = job.progress || 0;
              const imageName = job.image_display_name || job.image_name || "Selected image";
              const detectionInProgress = isDetectionJobActive(job);

              return (
                <div className="detection-status-panel" role="status" key={job.id}>
                  <div className="detection-status-head">
                    <div className="detection-status-copy">
                      <div className="detection-status-title">Start detection</div>
                      <div className="detection-status-image" title={imageName}>
                        {imageName}
                      </div>
                      <div className="detection-status-message">
                        {job.message || "Checking detection status"}
                      </div>
                    </div>
                    <div className="detection-status-actions">
                      <div className={`detection-status-badge detection-status-${String(job.status).toLowerCase()}`}>
                        {job.status}
                      </div>
                      <button
                        type="button"
                        className="detection-task-close"
                        aria-label={`Close detection task for ${imageName}`}
                        title="Close task"
                        onClick={() => closeDetectionTask(job.id)}
                      >
                        <MdIcon.MdClose />
                      </button>
                    </div>
                  </div>
                  <div className="progress-bar-track" aria-label={`${imageName} detection progress`}>
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${jobProgress}%` }}
                    />
                  </div>
                  <div className="detection-status-foot">
                    <span>{jobProgress}%</span>
                    {detectionInProgress ? (
                      <button type="button" onClick={() => fetchDetectionJob(job.id)}>
                        Refresh
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
            {exportJobs.map((job) => {
              const jobProgress = job.progress || 0;
              const imageName = job.image_display_name || job.image_name || "Selected image";
              const exportInProgress = isExportJobActive(job);
              const exportReady = job.status === "SUCCESS" && job.artifact_exists === true;

              return (
                <div className="detection-status-panel export-status-panel" role="status" key={`export-${job.id}`}>
                  <div className="detection-status-head">
                    <div className="detection-status-copy">
                      <div className="detection-status-title">Save data</div>
                      <div className="detection-status-image" title={imageName}>
                        {imageName}
                      </div>
                      <div className="detection-status-message">
                        {job.message || "Checking export status"}
                      </div>
                    </div>
                    <div className="detection-status-actions">
                      <div className={`detection-status-badge detection-status-${String(job.status).toLowerCase()}`}>
                        {job.status}
                      </div>
                      <button
                        type="button"
                        className="detection-task-close"
                        aria-label={`Close save data task for ${imageName}`}
                        title="Close task"
                        onClick={() => closeExportTask(job.id)}
                      >
                        <MdIcon.MdClose />
                      </button>
                    </div>
                  </div>
                  <div className="progress-bar-track" aria-label={`${imageName} save data progress`}>
                    <div
                      className="progress-bar-fill export-progress-fill"
                      style={{ width: `${jobProgress}%` }}
                    />
                  </div>
                  <div className="detection-status-foot">
                    <span>{jobProgress}%</span>
                    {exportInProgress ? (
                      <button type="button" onClick={() => fetchExportJob(job.id)}>
                        Refresh
                      </button>
                    ) : null}
                    {exportReady && String(job.image_id) === String(dataImage.id) ? (
                      <button type="button" onClick={download}>
                        Export
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}
        {displayedImageName && showImageNotification ? (
          <div className="image-display-notification" role="status" aria-live="polite">
            <div className="image-display-notification-text">
              Displaying image: <span>{displayedImageName}</span>
            </div>
            <button
              type="button"
              className="image-notification-close"
              aria-label="Close image notification"
              title="Close"
              onClick={() => setShowImageNotification(false)}
            >
              <MdIcon.MdClose />
            </button>
          </div>
        ) : null}
        {exportTooltip.visible && !canExportResult ? (
          <div
            className="export-unavailable-tooltip"
            style={{
              left: `${exportTooltip.x + 14}px`,
              top: `${exportTooltip.y + 14}px`,
            }}
            role="tooltip"
          >
            This function is only available when the data is saved.
          </div>
        ) : null}
        {imgDimensions && bounds && imgSrc ? (
          <MapContainer
            key={dataImage.id || imgSrc}
            center={center}
            zoom={0}
            minZoom={-3}
            scrollWheelZoom={true}
            crs={CRS.Simple}
            maxZoom={3}
            doubleClickZoom={false}
            zoomControl={false}
            whenCreated={(map) => {
              mapRef.current = map;
            }}
          >
            <ZoomControl position="topright" />
            <ImageOverlay url={imgSrc} bounds={bounds} opacity={1} zIndex={10} />
            <MarkerClusterGroup maxClusterRadius={30} iconCreateFunction={createClusterIcon}>
              <AddMarker
                childToParent={childToParent}
                scale={scale}
                scaleMeta={scaleMeta}
                image_height={dataImage.image_height}
                detectionHeight={dataImage.detection_height || dataImage.image_height}
                sourceHeight={dataImage.source_height || dataImage.image_height}
                metadata={imgMeta}
                imageId={dataImage.id}
                refreshKey={markerRefreshKey}
              />
            </MarkerClusterGroup>
          </MapContainer>
        ) : hasUploadedImage ? (
          <div className="map-loading-skeleton">
            <ReactLoading type={"spin"} color={"#888"} height={60} width={60} />
            <p style={{ color: '#aaa', marginTop: '16px' }}>Loading map...</p>
          </div>
        ) : (
          <div className="map-loading-skeleton map-empty-state" role="status" aria-live="polite">
            <p>No image is uploaded</p>
          </div>
        )}
          </>
        )}
      </div>
    </div>
  );
}

export default MapKambyan;
