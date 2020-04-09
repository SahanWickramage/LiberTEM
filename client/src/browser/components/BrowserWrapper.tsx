import * as React from "react";
import { connect, useSelector } from "react-redux";
import { Button, Icon } from "semantic-ui-react";
import { RootReducer } from "../../store";
import * as browserActions from '../actions';
import FileBrowser from "./FileBrowser";
import libertem from '../../images/libertem_logo.svg'
import github from '../../images/github_logo.png'

export const mapStateToProps = (state: RootReducer) => {
    return {
        isOpen: state.browser.isOpen,
    }
}

export const mapDispatchToProps = {
    open: browserActions.Actions.open,
}

type MergedProps = ReturnType<typeof mapStateToProps> & DispatchProps<typeof mapDispatchToProps>;

const BrowserWrapper: React.SFC<MergedProps> = ({ isOpen, open}) => {
    const noOfDatasets = useSelector((state: RootReducer) => state.datasets.ids).length;
    const isVisible = useSelector((state: RootReducer) => state.openDataset.formVisible);
    if (!isOpen) {
        if (!noOfDatasets && !isVisible) {
            return ( 
                <div>
                    <div style={{textAlign: 'center'}}>
                        <h1>Get Started With LiberTEM</h1>
                        <img src={libertem} alt="libertem" style={{paddingTop: '5%', paddingBottom: '5%', opacity: '0.6'}}/>
                        <div style={{marginLeft: '30%', marginRight: '30%', paddingBottom: '5%'}}>
                            <text>
                            LiberTEM is an open source platform for high-throughput distributed processing of pixelated scanning transmission electron microscopy (STEM) data. Click on "Browse" to select the dataset you want to analyze.
                            </text>
                        </div>
                        <Button icon={true} labelPosition="left" onClick={open} color='blue'>
                            <Icon name='add' />
                            Browse
                        </Button>  
                        <div style={{paddingTop: '5%', paddingBottom: '5%'}}>
                            <a href={'https://libertem.github.io/LiberTEM/'} target='_blank'>Learn more about LiberTEM</a>
                            <br/>
                            <br/>
                            <img src={github} alt="github" style={{height: '25px', width: '25px'}}/>
                            <a href={'https://github.com/LiberTEM/LiberTEM'} target='_blank'> Star us on GitHub</a>
                        </div>
                    </div>
                </div>
            );
        }
        return ( 
            <div>
                <div style={{textAlign: 'center'}}>
                    <Button icon={true} labelPosition="left" onClick={open} color='blue'>
                        <Icon name='add' />
                        Browse
                    </Button>
                </div>
            </div>
        );
    }
    return (
        <FileBrowser />
    );
    
}

export default connect(mapStateToProps, mapDispatchToProps)(BrowserWrapper)