import React from 'react';
import Modal from "react-bootstrap/Modal";
import "bootstrap/dist/css/bootstrap.min.css";
import Button from 'react-bootstrap/Button';



function GenerateFlag(props) {

    
    return (
        <Modal
            {...props}
            size="lg"
            aria-labelledby="contained-modal-title-vcenter"
            centered
        >
            <Modal.Header closeButton>
                <Modal.Title id="contained-modal-title-vcenter">
                    Unable to Export Result
                </Modal.Title>
            </Modal.Header>
            <Modal.Body>
                <div style={{ textAlign: 'center', padding: '12px 0' }}>
                    <div className="modal-warning-icon modal-warning-icon--danger">⚠️</div>
                    <p style={{ marginTop: '8px' }}>Please save data before exporting the result.</p>
                </div>
            </Modal.Body>
            <Modal.Footer>
                <Button onClick={props.onHide}>Close</Button>
            </Modal.Footer>
        </Modal>
    )
}

export default GenerateFlag
